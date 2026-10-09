"""FastAPI app: the local AI agent's API, the simulated platforms (/mock) and the UI (/)."""
import csv
import io
import json
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, connectors, llm, mock_cloud, sync, vault
from .config import CFG, WEB_DIR


def _agent():
    time.sleep(1.5)  # let the server start listening before the first sync
    first = True
    while True:
        try:
            sync.Net.real_ok = sync.check_internet()
            c = vault.connect()
            if first or time.time() - _agent.last_sync >= CFG["auto_sync_seconds"]:
                sync.sync_all(c)
                _agent.last_sync = time.time()
                first = False
            if c.execute("SELECT 1 FROM changes WHERE status='Queued' LIMIT 1").fetchone():
                sync.push_changes(c)
            if vault.get_meta(c, "index_stale", "1") != "0":
                try:
                    n = ai.ensure_index(c)
                    if n:
                        print(f"   indexed {n} new/changed records for AI search")
                except llm.OllamaError:
                    pass
            c.close()
        except Exception as e:
            print("background agent error:", e)
        time.sleep(5)


_agent.last_sync = 0.0


@asynccontextmanager
async def lifespan(app):
    vault.connect().close()
    mock_cloud.data()
    threading.Thread(target=_agent, daemon=True).start()
    yield


app = FastAPI(title="All Is Well AI", lifespan=lifespan)
app.include_router(mock_cloud.router)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def db():
    return vault.connect()


def ndjson(events):
    def wrap():
        try:
            for ev in events:
                yield json.dumps(ev) + "\n"
        except llm.OllamaError as e:
            yield json.dumps({"type": "error", "message": e.message, "fix": e.fix}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": "Something went wrong.", "fix": str(e)}) + "\n"
    return StreamingResponse(wrap(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


# ---------------- status ----------------
def ollama_state():
    try:
        models = llm.list_models()
        return "ready" if llm.has_model(CFG["llm_model"], models) and llm.has_model(CFG["embed_model"], models) else "model missing"
    except llm.OllamaError:
        return "not running"


@app.get("/health")
def health():
    c = db()
    st = vault.stats(c)
    o = ollama_state()
    return {"status": "ok" if o == "ready" and st["total"] else "degraded", "ollama": o, "llm_model": CFG["llm_model"],
            "embed_model": CFG["embed_model"], "internet": sync.Net.online(), "vault_records": st["total"],
            "indexed": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], "by_source": st["by_source"]}


@app.get("/api/status")
def status():
    c = db()
    conns = {r["source"]: r for r in vault.rows(c.execute("SELECT * FROM connections"))}
    st = vault.stats(c)
    out = []
    for src, (name, what, _) in connectors.CONNECTORS.items():
        r = conns.get(src, {})
        out.append({"source": src, "name": name, "what": what, "state": r.get("state", "never synced"),
                    "last_success_at": r.get("last_success_at"), "last_attempt_at": r.get("last_attempt_at"),
                    "error": r.get("last_error"), "records": st["by_source"].get(src, 0),
                    "switch": mock_cloud.STATE["status"][src]})
    imports = [{"source": s, "records": n} for s, n in st["by_source"].items() if s.startswith("import:")]
    return {"internet": sync.Net.online(), "simulated_offline": sync.Net.simulated, "connections": out, "imports": imports,
            "vault": st, "ollama": ollama_state(), "llm_model": CFG["llm_model"], "embed_model": CFG["embed_model"],
            "business": CFG["business_name"],
            "queued": c.execute("SELECT COUNT(*) FROM changes WHERE status='Queued'").fetchone()[0],
            "last_synced_at": c.execute("SELECT MAX(last_success_at) FROM connections").fetchone()[0]}


class Flag(BaseModel):
    on: bool


@app.post("/api/internet-off")
def internet_off(f: Flag):
    sync.Net.simulated = f.on
    if not f.on:
        threading.Thread(target=lambda: (sync.push_changes(), sync.sync_all()), daemon=True).start()
    return {"internet": sync.Net.online()}


class PlatformState(BaseModel):
    status: str


@app.post("/api/platform/{source}")
def set_platform(source: str, p: PlatformState):
    if source not in mock_cloud.PLATFORMS or p.status not in ("up", "down", "shutdown"):
        raise HTTPException(400, "Unknown platform or state")
    mock_cloud.set_status(source, p.status)
    c = db()
    res = sync.sync_source(c, source)
    if p.status == "up":
        sync.push_changes(c)
    return res


@app.post("/api/platform-activity")
def platform_activity():
    msg = mock_cloud.simulate_activity()
    return {"message": msg}


@app.post("/api/sync")
def sync_now():
    c = db()
    res = sync.sync_all(c)
    sync.push_changes(c)
    return {"results": res}


@app.get("/api/sync-runs")
def sync_runs():
    return vault.rows(db().execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 40"))


# ---------------- vault browsing ----------------
@app.get("/api/records")
def records(entity: str = "", source: str = "", q: str = "", limit: int = 500):
    where, params = ["1=1"], []
    if entity:
        where.append("entity=?"); params.append(entity)
    if source:
        where.append("source=?"); params.append(source)
    if q:
        where.append("(title LIKE ? OR company LIKE ? OR person LIKE ? OR summary LIKE ?)"); params += [f"%{q}%"] * 4
    recs = vault.find(db(), " AND ".join(where), params, order="entity, due_date, title", limit=limit)
    return [{k: r[k] for k in ("uid", "source", "entity", "title", "company", "person", "status", "amount", "due_date",
                               "version", "last_synced_at", "local_edit")} for r in recs]


@app.get("/api/record/{uid}")
def record(uid: str):
    c = db()
    r = vault.find(c, "uid=?", (uid,))
    if not r:
        raise HTTPException(404, "Not in the vault")
    r = r[0]
    related = []
    if r["company"] and r["company"] != ai.INTERNAL and r["entity"] != "lead":
        related = vault.find(c, "company=? AND uid!=?", (r["company"], uid), order="entity, due_date")
    elif r["entity"] == "employee":
        related = vault.find(c, f"{ai.OPEN_TASK} AND person LIKE ?", (f"%{r['title']}%",), order="due_date")
    versions = vault.rows(c.execute("SELECT version, replaced_at, summary FROM record_versions WHERE uid=? ORDER BY version DESC", (uid,)))
    changes = vault.rows(c.execute("SELECT * FROM changes WHERE uid=? ORDER BY id DESC", (uid,)))
    return {"record": {**r, "raw": json.loads(r["raw"]), "source_name": ai.source_name(r["source"]), "label": vault.label(r)},
            "related": [{k: x[k] for k in ("uid", "entity", "title", "status", "amount", "due_date")} for x in related[:40]],
            "versions": versions, "changes": changes}


# ---------------- AI ----------------
class Ask(BaseModel):
    question: str


@app.post("/api/ask")
def ask(a: Ask):
    def gen():
        c = db()
        t0 = time.time()
        ai.ensure_index(c)
        facts = ai.facts_for(c, a.question)
        uids = list(dict.fromkeys(u for u, _ in facts if u))
        yield {"type": "sources", "ids": uids, "labels": vault.labels(c, uids)}
        for piece in llm.chat_stream(ai.ask_messages(a.question, facts), max_tokens=400):
            yield {"type": "token", "text": piece}
        yield {"type": "done", "seconds": round(time.time() - t0, 1), "model": CFG["llm_model"],
               "last_synced_at": c.execute("SELECT MAX(last_success_at) FROM connections").fetchone()[0],
               "internet": sync.Net.online()}
    return ndjson(gen())


@app.post("/api/report")
def report():
    def gen():
        c = db()
        t0 = time.time()
        f = ai.report_facts(c)
        uids = [r["uid"] for k in ("overdue", "due_soon", "tasks_today", "tasks_late", "tasks_week", "deals", "leads", "contacts") for r in f[k]]
        yield {"type": "facts", "facts": f, "labels": vault.labels(c, list(dict.fromkeys(uids)))}
        for piece in llm.chat_stream(ai.report_messages(f), max_tokens=450):
            yield {"type": "token", "text": piece}
        yield {"type": "done", "seconds": round(time.time() - t0, 1)}
    return ndjson(gen())


class DraftReq(BaseModel):
    uid: str
    instruction: str = ""


@app.post("/api/draft")
def draft(d: DraftReq):
    c = db()
    ctx = ai.draft_context(c, d.uid)
    if not ctx:
        raise HTTPException(404, "Not in the vault")

    def gen():
        ct = ctx["contact"]
        yield {"type": "meta", "to": (ct or {}).get("email") or "", "to_name": (ct or {}).get("title", ""),
               "subject": ctx["subject"]}
        for piece in llm.chat_stream(ai.draft_messages(ctx, d.instruction), max_tokens=280, temperature=0.4):
            yield {"type": "token", "text": piece}
        yield {"type": "done"}
    return ndjson(gen())


# ---------------- local changes (queued while platforms are down) ----------------
class Email(BaseModel):
    to: str
    subject: str
    body: str
    uid: str | None = None


@app.post("/api/changes/email")
def queue_email(e: Email):
    return sync.queue_change(db(), "email", "email", e.uid, e.model_dump(), f"Email to {e.to}: {e.subject}")


class TaskStatus(BaseModel):
    uid: str
    status: str


@app.post("/api/changes/task-status")
def queue_task_status(t: TaskStatus):
    c = db()
    r = c.execute("SELECT * FROM records WHERE uid=? AND entity='task'", (t.uid,)).fetchone()
    if not r:
        raise HTTPException(404, "Task not found")
    status = {"zoho_projects": {"done": "Closed", "open": "Open"}, "clickup": {"done": "complete", "open": "to do"}}[r["source"]][t.status]
    c.execute("UPDATE records SET status=?, local_edit=1 WHERE uid=?", (status, t.uid))  # works locally right away
    c.commit()
    vault.set_meta(c, "index_stale", "1")
    return sync.queue_change(c, "task_status", r["source"], t.uid, {"status": status},
                             f"Mark '{r['title']}' as {status} in {ai.source_name(r['source'])}")


class Note(BaseModel):
    uid: str          # a company
    content: str


@app.post("/api/changes/note")
def queue_note(n: Note):
    c = db()
    r = c.execute("SELECT * FROM records WHERE uid=? AND entity='company'", (n.uid,)).fetchone()
    if not r:
        raise HTTPException(404, "Company not found")
    return sync.queue_change(c, "note", "zoho_crm", n.uid, {"title": "Note added offline", "content": n.content,
                             "company": r["title"], "company_source_id": r["source_id"]},
                             f"Add note to {r['title']} in Zoho CRM")


@app.get("/api/changes")
def changes():
    return vault.rows(db().execute("SELECT * FROM changes ORDER BY id DESC"))


# ---------------- AI import of any export file ----------------
class ImportFile(BaseModel):
    filename: str
    content: str
    entity: str | None = None
    mapping: dict | None = None


def parse_file(f: ImportFile) -> list[dict]:
    text = f.content.lstrip("﻿")
    if f.filename.lower().endswith(".json"):
        j = json.loads(text)
        if isinstance(j, dict):  # e.g. {"data": [...]}, {"results": [...]}
            j = next((v for v in j.values() if isinstance(v, list)), [j])
        return [x if isinstance(x, dict) else {"value": x} for x in j]
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


@app.post("/api/import/preview")
def import_preview(f: ImportFile):
    try:
        rows = parse_file(f)
    except Exception as e:
        raise HTTPException(400, f"Couldn't read that file: {e}")
    if not rows:
        raise HTTPException(400, "The file has no rows.")
    headers = list(rows[0].keys())
    proposal = ai.propose_mapping(headers, rows[:3])
    return {"rows": len(rows), "headers": headers, "sample": rows[:3], **proposal,
            "entities": ai.ENTITIES, "fields": ai.FIELDS}


@app.post("/api/import/commit")
def import_commit(f: ImportFile):
    rows = parse_file(f)
    return ai.import_rows(db(), f.filename, f.entity or "record", f.mapping or {}, rows)


# ---------------- export ----------------
@app.get("/api/export")
def export():
    name, data = vault.export_zip(db())
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})

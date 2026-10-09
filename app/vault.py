"""The local vault: one SQLite file on this computer that holds a copy of everything from every platform.

Each record keeps the platform's original JSON (raw) plus a normalized view (entity, title, company, person,
status, amount, due_date) so the AI can answer across platforms. Changed records keep their old versions."""
import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import date, datetime

from .config import DB_PATH, VAULT_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  uid TEXT PRIMARY KEY, source TEXT, source_id TEXT, entity TEXT, title TEXT, company TEXT, person TEXT,
  status TEXT, amount REAL, due_date TEXT, email TEXT, phone TEXT, summary TEXT, data TEXT, raw TEXT,
  hash TEXT, version INTEGER DEFAULT 1, first_seen TEXT, last_synced_at TEXT, local_edit INTEGER DEFAULT 0,
  UNIQUE(source, source_id));
CREATE INDEX IF NOT EXISTS ix_records_entity ON records(entity);
CREATE INDEX IF NOT EXISTS ix_records_company ON records(company);
CREATE TABLE IF NOT EXISTS record_versions (uid TEXT, version INTEGER, raw TEXT, summary TEXT, replaced_at TEXT);
CREATE TABLE IF NOT EXISTS sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, started_at TEXT,
  finished_at TEXT, status TEXT, message TEXT, fetched INTEGER, created INTEGER, updated INTEGER);
CREATE TABLE IF NOT EXISTS connections (source TEXT PRIMARY KEY, name TEXT, state TEXT, last_success_at TEXT,
  last_attempt_at TEXT, last_error TEXT);
CREATE TABLE IF NOT EXISTS chunks (uid TEXT PRIMARY KEY, hash TEXT, embedding BLOB);
CREATE TABLE IF NOT EXISTS changes (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, source TEXT, uid TEXT,
  payload TEXT, description TEXT, status TEXT, created_at TEXT, pushed_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS counters (prefix TEXT PRIMARY KEY, n INTEGER);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

PREFIX = {"company": "CO", "contact": "CT", "deal": "DL", "note": "NT", "project": "PR", "task": "TK",
          "invoice": "INV", "lead": "LD", "employee": "EMP", "record": "IM"}
ENTITY_LABEL = {"company": "Company", "contact": "Contact", "deal": "Deal", "note": "Note", "project": "Project",
                "task": "Task", "invoice": "Invoice", "lead": "Lead", "employee": "Employee", "record": "Record"}


def connect(path=None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def get_meta(c, key, default=None):
    r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_meta(c, key, value):
    c.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    c.commit()


def _next_uid(c, entity: str, preferred: str | None = None) -> str:
    if preferred and not c.execute("SELECT 1 FROM records WHERE uid=?", (preferred,)).fetchone():
        return preferred
    prefix = PREFIX.get(entity, "R")
    c.execute("INSERT INTO counters VALUES(?,0) ON CONFLICT(prefix) DO NOTHING", (prefix,))
    c.execute("UPDATE counters SET n=n+1 WHERE prefix=?", (prefix,))
    n = c.execute("SELECT n FROM counters WHERE prefix=?", (prefix,)).fetchone()[0]
    return f"{prefix}-{n:02d}"


def upsert(c, source: str, source_id: str, entity: str, norm: dict, raw: dict, synced_at: str) -> str:
    """Insert or update one record. Returns 'created', 'updated' or 'same'."""
    raw_s = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha1(raw_s.encode()).hexdigest()
    old = c.execute("SELECT uid, hash, version, raw, summary FROM records WHERE source=? AND source_id=?",
                    (source, source_id)).fetchone()
    cols = dict(entity=entity, title=norm.get("title"), company=norm.get("company"), person=norm.get("person"),
                status=norm.get("status"), amount=norm.get("amount"), due_date=norm.get("due_date"),
                email=norm.get("email"), phone=norm.get("phone"), summary=norm.get("summary"),
                data=json.dumps(norm.get("data", {}), ensure_ascii=False), raw=raw_s, hash=h, last_synced_at=synced_at)
    if old is None:
        uid = _next_uid(c, entity, norm.get("preferred_uid"))
        c.execute(f"INSERT INTO records (uid, source, source_id, first_seen, {','.join(cols)}) "
                  f"VALUES (?,?,?,?,{','.join('?' * len(cols))})", (uid, source, source_id, synced_at, *cols.values()))
        return "created"
    if old["hash"] == h:
        c.execute("UPDATE records SET last_synced_at=? WHERE uid=?", (synced_at, old["uid"]))
        return "same"
    c.execute("INSERT INTO record_versions VALUES (?,?,?,?,?)", (old["uid"], old["version"], old["raw"], old["summary"], synced_at))
    c.execute(f"UPDATE records SET {','.join(k + '=?' for k in cols)}, version=version+1, local_edit=0 WHERE uid=?",
              (*cols.values(), old["uid"]))
    return "updated"


def label(r: dict) -> str:
    return f"{ENTITY_LABEL.get(r['entity'], 'Record')}: {r['title']}" if r["entity"] != "invoice" else f"Invoice #{r['uid']}"


def labels(c, uids) -> dict:
    out = {}
    for u in uids:
        r = c.execute("SELECT uid, entity, title FROM records WHERE uid=?", (u,)).fetchone()
        if r:
            out[u] = label(dict(r))
    return out


def invoice_status(r: dict) -> str:
    if r["entity"] != "invoice":
        return r["status"]
    if r["status"] == "paid":
        return "paid"
    return "overdue" if (r["due_date"] or "9999") < today() else "unpaid"


def find(c, where="1=1", params=(), order="entity, title", limit=None) -> list[dict]:
    q = f"SELECT * FROM records WHERE {where} ORDER BY {order}" + (f" LIMIT {int(limit)}" if limit else "")
    out = rows(c.execute(q, params))
    for r in out:
        r["status"] = invoice_status(r)
    return out


def stats(c) -> dict:
    by_source = {r["source"]: r["n"] for r in rows(c.execute("SELECT source, COUNT(*) n FROM records GROUP BY source"))}
    by_entity = {r["entity"]: r["n"] for r in rows(c.execute("SELECT entity, COUNT(*) n FROM records GROUP BY entity"))}
    size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    versions = c.execute("SELECT COUNT(*) FROM record_versions").fetchone()[0]
    return {"by_source": by_source, "by_entity": by_entity, "total": sum(by_source.values()),
            "size_mb": round(size / 1e6, 2), "versions": versions}


# ---------------- export: your data, in open formats ----------------
EXPORT_COLS = ["uid", "source", "source_id", "entity", "title", "company", "person", "status", "amount",
               "due_date", "email", "phone", "summary", "last_synced_at"]


def export_zip(c) -> tuple[str, bytes]:
    """Everything in the vault as CSV (per type), the platforms' original JSON, and a readable index."""
    buf = io.BytesIO()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        recs = find(c)
        for entity in sorted({r["entity"] for r in recs}):
            s = io.StringIO()
            w = csv.DictWriter(s, fieldnames=EXPORT_COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows([r for r in recs if r["entity"] == entity])
            z.writestr(f"csv/{entity}s.csv", s.getvalue())
        for source in sorted({r["source"] for r in recs}):
            z.writestr(f"original_json/{source}.json",
                       json.dumps([json.loads(r["raw"]) for r in recs if r["source"] == source], indent=2, ensure_ascii=False))
        st = stats(c)
        z.writestr("README.txt", f"Business data export from All Is Well AI ({stamp}).\n"
                   f"{st['total']} records from {len(st['by_source'])} sources.\n"
                   "csv/ = one spreadsheet per record type (opens in Excel/Google Sheets).\n"
                   "original_json/ = each platform's records exactly as its API returned them.\n")
    data = buf.getvalue()
    (VAULT_DIR / "exports").mkdir(parents=True, exist_ok=True)
    name = f"business-export_{stamp}.zip"
    (VAULT_DIR / "exports" / name).write_bytes(data)
    return name, data

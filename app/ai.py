"""Local AI on the vault: embeddings search + exact SQL facts -> local LLM, with citations.
Nothing in this file calls the internet; it only talks to Ollama on this computer."""
import json
import re
from datetime import date, timedelta

import numpy as np

from . import llm, vault
from .config import CFG

SOURCE_NAME = {"zoho_crm": "Zoho CRM", "zoho_projects": "Zoho Projects", "zoho_books": "Zoho Books",
               "hubspot": "HubSpot", "clickup": "ClickUp", "bamboohr": "BambooHR"}
OPEN_TASK = "entity='task' AND lower(status) NOT IN ('closed','complete')"
OPEN_DEAL = "entity='deal' AND status NOT LIKE 'Closed%'"
INTERNAL = "Web Innovation Experts (internal)"
money = lambda v: f"AUD {float(v or 0):,.0f}"


def source_name(s: str) -> str:
    return SOURCE_NAME.get(s, s.replace("import:", "Imported file "))


def record_text(r: dict) -> str:
    st = vault.invoice_status(r)
    bits = [f"[{r['uid']}] {vault.ENTITY_LABEL.get(r['entity'], 'Record')}: {r['title']}."]
    if r.get("company") and r["entity"] not in ("company",):
        bits.append(f"Company: {r['company']}.")
    if r.get("person") and r["entity"] not in ("contact", "employee"):
        bits.append(f"Person: {r['person']}.")
    if st:
        bits.append(f"Status: {st.upper() if r['entity'] == 'invoice' else st}.")
    if r.get("amount") is not None:
        bits.append(f"Amount: {money(r['amount'])}.")
    if r.get("due_date") and r["entity"] != "note":
        bits.append(f"{'Closes' if r['entity'] == 'deal' else 'Due'}: {r['due_date']}.")
    if r.get("summary"):
        bits.append(r["summary"])
    bits.append(f"(Source: {source_name(r['source'])})")
    return " ".join(bits)


# ---------------- embeddings index (incremental) ----------------
_cache = {"version": None, "uids": [], "m": None}


def ensure_index(c) -> int:
    if vault.get_meta(c, "index_stale", "1") == "0" and \
            c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == c.execute("SELECT COUNT(*) FROM records").fetchone()[0]:
        return 0
    recs = vault.find(c)
    have = {r["uid"]: r["hash"] for r in vault.rows(c.execute("SELECT uid, hash FROM chunks"))}
    todo = [r for r in recs if have.get(r["uid"]) != r["hash"]]
    for i in range(0, len(todo), 32):
        batch = todo[i:i + 32]
        vecs = llm.embed([record_text(r) for r in batch])
        c.executemany("INSERT OR REPLACE INTO chunks VALUES (?,?,?)",
                      [(r["uid"], r["hash"], v.tobytes()) for r, v in zip(batch, vecs)])
    c.execute(f"DELETE FROM chunks WHERE uid NOT IN (SELECT uid FROM records)")
    c.commit()
    vault.set_meta(c, "index_stale", "0")
    vault.set_meta(c, "index_version", vault.now() + str(len(todo)))
    return len(todo)


def search(c, q: str, k: int | None = None) -> list[str]:
    ver = vault.get_meta(c, "index_version")
    if _cache["version"] != ver:
        rs = c.execute("SELECT uid, embedding FROM chunks").fetchall()
        _cache.update(version=ver, uids=[r[0] for r in rs],
                      m=np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rs]) if rs else None)
    if _cache["m"] is None:
        return []
    qv = llm.embed([q], kind="query")[0]
    order = np.argsort(-(_cache["m"] @ qv))[: k or CFG["top_k"]]
    return [_cache["uids"][i] for i in order]


# ---------------- exact lookups ----------------
GENERIC = {"the", "of", "co.", "co", "&", "and", "group", "studios", "studio", "company", "inc", "ltd"}


def match_companies(c, q: str) -> list[str]:
    ql = q.lower()
    out = []
    for (name,) in c.execute("SELECT DISTINCT company FROM records WHERE entity='company' OR entity='lead'"):
        if not name or name == INTERNAL:
            continue
        n = name.lower()
        words = [w for w in re.split(r"\s+", n) if w not in GENERIC]
        if n in ql or (len(words) >= 2 and " ".join(words[:2]) in ql) or (words and len(words[0]) >= 6 and re.search(rf"\b{re.escape(words[0])}\b", ql)):
            out.append(name)
    return out


def match_people(c, q: str) -> list[str]:
    ql = q.lower()
    out = []
    for (name,) in c.execute("SELECT title FROM records WHERE entity='employee'"):
        first = name.split()[0].lower()
        if name.lower() in ql or re.search(rf"\b{re.escape(first)}\b", ql):
            out.append(name)
    return out


def has(q, *words):
    return any(w in q for w in words)


def facts_for(c, q: str) -> list[tuple[str, str]]:
    """(uid, text) pairs: exact facts first, then semantic search hits."""
    ql = q.lower()
    t = vault.today()
    week = (date.today() + timedelta(days=7)).isoformat()
    facts: list[tuple[str, str]] = []

    def add(recs, n=None):
        for r in recs[:n]:
            facts.append((r["uid"], record_text(r)))

    companies, people = match_companies(c, q), match_people(c, q)
    for name in companies:
        recs = vault.find(c, "company=?", (name,), order="CASE entity WHEN 'company' THEN 0 WHEN 'invoice' THEN 1 "
                          "WHEN 'deal' THEN 2 WHEN 'project' THEN 3 WHEN 'note' THEN 4 WHEN 'task' THEN 5 ELSE 6 END, due_date")
        recs = [r for r in recs if not (r["entity"] == "task" and r["status"].lower() in ("closed", "complete"))]
        inv = [r for r in recs if r["entity"] == "invoice" and r["status"] != "paid"]
        facts.append(("", f"EXACT LOOKUP: {name} has {len(inv)} unpaid/overdue invoice(s) totalling "
                          f"{money(sum(r['amount'] for r in inv))}." if inv else f"EXACT LOOKUP: {name} has no unpaid invoices."))
        add(recs, 14)
    for p in people:
        add(vault.find(c, "entity='employee' AND title=?", (p,)))
        tasks = vault.find(c, f"{OPEN_TASK} AND person LIKE ?", (f"%{p}%",), order="due_date")
        facts.append(("", f"EXACT LOOKUP: {p} has {len(tasks)} open task(s)."))
        add(tasks, 10)
    if not companies and has(ql, "owe", "unpaid", "overdue invoice", "invoice", "outstanding", "receivable", "paid", "cash", "money"):
        inv = vault.find(c, "entity='invoice'", order="due_date")
        od = [r for r in inv if r["status"] == "overdue"]
        un = [r for r in inv if r["status"] == "unpaid"]
        facts.append(("", f"EXACT LOOKUP: {len(od)} overdue invoices totalling {money(sum(r['amount'] for r in od))}; "
                          f"{len(un)} unpaid not yet due totalling {money(sum(r['amount'] for r in un))}."))
        add(sorted(od, key=lambda r: -r["amount"]), 10)
    if not companies and not people and has(ql, "task", "deadline", "due", "today", "this week", "working on", "sprint", "late", "behind"):
        add(vault.find(c, f"{OPEN_TASK} AND due_date <= ?", (week,), order="due_date"), 14)
    if has(ql, "deal", "pipeline", "closing", "sales", "won", "revenue forecast"):
        deals = vault.find(c, OPEN_DEAL, order="due_date")
        facts.append(("", f"EXACT LOOKUP: {len(deals)} open deals worth {money(sum(r['amount'] or 0 for r in deals))} in total."))
        add(deals, 10)
    if has(ql, "lead", "prospect", "hubspot", "inbound", "enquir", "inquir"):
        add(vault.find(c, "entity='lead'", order="CASE status WHEN 'opportunity' THEN 0 WHEN 'salesqualifiedlead' THEN 1 ELSE 2 END"), 10)
    if not people and has(ql, "who is", "who's", "employee", "staff", "team", "our ", "hr", "department"):
        add(vault.find(c, "entity='employee'"), 12)

    seen = {u for u, _ in facts if u}
    try:
        for uid in search(c, q):
            if uid not in seen:
                r = vault.find(c, "uid=?", (uid,))
                if r:
                    facts.append((uid, record_text(r[0])))
                    seen.add(uid)
    except llm.OllamaError:
        if not facts:
            raise
    return facts[:24]


ASK_SYSTEM = """You are the local AI assistant for {biz}. You answer from the company's own data vault, which is a
copy of its Zoho CRM, Zoho Projects, Zoho Books, HubSpot, ClickUp and BambooHR data kept on this computer.
Today is {today}. Answer ONLY from the SOURCES.
- Cite every fact with the record ID in square brackets exactly as shown, e.g. [INV-2042] or [TK-07].
- Lines starting with EXACT LOOKUP are computed from the database; trust them for totals and counts.
- If the sources don't contain the answer, say "I couldn't find that in your vault." Never invent names, amounts or dates.
- Amounts are Australian dollars, written like AUD 38,000.
- Be brief and practical: 2 to 6 sentences or a short bullet list."""


def ask_messages(q: str, facts):
    ctx = "\n".join(f"- {t}" for _, t in facts)
    return [{"role": "system", "content": ASK_SYSTEM.format(biz=CFG["business_name"], today=date.today().strftime("%A %d %B %Y"))},
            {"role": "user", "content": f"SOURCES:\n{ctx}\n\nQUESTION: {q}"}]


# ---------------- continuity report ----------------
def report_facts(c) -> dict:
    t, week, fortnight = vault.today(), (date.today() + timedelta(days=7)).isoformat(), (date.today() + timedelta(days=14)).isoformat()
    inv = vault.find(c, "entity='invoice'", order="due_date")
    od = sorted([r for r in inv if r["status"] == "overdue"], key=lambda r: -r["amount"])
    due_soon = [r for r in inv if r["status"] == "unpaid" and r["due_date"] <= week]
    tasks_today = vault.find(c, f"{OPEN_TASK} AND due_date = ?", (t,), order="person")
    tasks_late = vault.find(c, f"{OPEN_TASK} AND due_date < ?", (t,), order="due_date")
    tasks_week = vault.find(c, f"{OPEN_TASK} AND due_date > ? AND due_date <= ?", (t, week), order="due_date")
    deals = vault.find(c, f"{OPEN_DEAL} AND due_date <= ?", (fortnight,), order="due_date")
    leads = vault.find(c, "entity='lead' AND status IN ('opportunity','salesqualifiedlead')")
    conns = vault.rows(c.execute("SELECT * FROM connections ORDER BY name"))
    counts = vault.stats(c)["by_source"]
    for x in conns:
        x["records"] = counts.get(x["source"], 0)
    companies = []
    for r in od + tasks_today + tasks_late:
        if r["company"] and r["company"] != INTERNAL and r["company"] not in companies:
            companies.append(r["company"])
    contacts = []
    for name in companies[:8]:
        ct = vault.find(c, "entity='contact' AND company=?", (name,), limit=1)
        if ct:
            contacts.append(ct[0])
    return {"date": t, "connections": conns, "overdue": od, "overdue_total": sum(r["amount"] for r in od),
            "due_soon": due_soon, "due_soon_total": sum(r["amount"] for r in due_soon), "tasks_today": tasks_today,
            "tasks_late": tasks_late, "tasks_week": tasks_week, "deals": deals,
            "deals_total": sum(r["amount"] or 0 for r in deals), "leads": leads, "contacts": contacts}


def report_text(f: dict) -> str:
    L = ["PLATFORMS:"] + [f"- {x['name']}: {x['state']}, {x['records']} records saved locally, last good sync {x['last_success_at']}" for x in f["connections"]]
    L.append(f"OVERDUE INVOICES: {len(f['overdue'])}, total {money(f['overdue_total'])}")
    L += [f"- [{r['uid']}] {r['company']} {money(r['amount'])} due {r['due_date']}" for r in f["overdue"][:8]]
    L.append(f"INVOICES DUE IN 7 DAYS: {len(f['due_soon'])}, total {money(f['due_soon_total'])}")
    L.append("TASKS DUE TODAY:")
    L += [f"- [{r['uid']}] {r['title']} ({r['company']}), {r['person']}" for r in f["tasks_today"]] or ["- none"]
    L.append("OVERDUE TASKS:")
    L += [f"- [{r['uid']}] {r['title']} ({r['company']}), {r['person']}, due {r['due_date']}" for r in f["tasks_late"][:8]] or ["- none"]
    L.append(f"DEALS CLOSING IN 14 DAYS: {len(f['deals'])}, worth {money(f['deals_total'])}")
    L += [f"- [{r['uid']}] {r['title']} {money(r['amount'])} ({r['status']}) closes {r['due_date']}" for r in f["deals"][:6]]
    L.append("HOT LEADS:")
    L += [f"- [{r['uid']}] {r['title']}: {r['summary'][-110:]}" for r in f["leads"][:4]]
    L.append("KEY CONTACTS:")
    L += [f"- [{r['uid']}] {r['title']} at {r['company']}, {r['email']}, {r['phone']}" for r in f["contacts"]]
    return "\n".join(L)


REPORT_SYSTEM = """You write a short business continuity report for an agency whose cloud platforms may be down.
Use ONLY the FACTS. Never add numbers, names or dates not in the FACTS. Cite record IDs in square brackets exactly as shown.
Format exactly:
## Situation
One or two sentences: which platforms are reachable, and that all data is safe in the local vault.
## Do today
3 to 5 bullets, most urgent first (tasks due today, overdue work, biggest overdue invoices).
## Money
2 bullets: overdue total and what is due this week; one deal to push.
## Who to contact
Up to 3 bullets: name, email or phone, and why.
Keep every bullet under 25 words."""


def report_messages(f):
    return [{"role": "system", "content": REPORT_SYSTEM}, {"role": "user", "content": "FACTS:\n" + report_text(f)}]


# ---------------- drafting ----------------
def draft_context(c, uid: str):
    r = vault.find(c, "uid=?", (uid,))
    if not r:
        return None
    r = r[0]
    company = r["company"] if r["entity"] != "employee" else None
    contact = None
    if r["entity"] in ("contact", "lead"):
        contact = r
    elif company:
        ct = vault.find(c, "entity='contact' AND company=?", (company,), limit=1)
        contact = ct[0] if ct else None
    related = [r] + (vault.find(c, "company=? AND entity IN ('invoice','deal','note','project') AND uid!=?", (company, uid)) if company else [])
    related = [x for x in related if not (x["entity"] == "invoice" and x["status"] == "paid")][:8]
    if r["entity"] == "invoice" and r["status"] != "paid":
        subject, task = f"Friendly reminder: {r['uid']} ({money(r['amount'])})", "Write a polite payment reminder for this invoice."
    elif r["entity"] == "lead":
        subject, task = f"Following up from {CFG['business_name']}", "Write a warm follow-up to this lead about their enquiry."
    else:
        subject, task = f"Update from {CFG['business_name']}", "Write a short, warm status update and check-in."
    return {"record": r, "contact": contact, "subject": subject, "task": task,
            "facts": "\n".join(record_text(x) for x in related)}


def draft_messages(ctx, instruction: str = ""):
    name = ctx["contact"]["title"].split(" (")[0] if ctx["contact"] else "there"
    return [{"role": "system", "content":
             f"You draft short client emails for {CFG['business_name']}, a marketing agency. Warm, clear, professional. "
             "Use ONLY the facts; never invent amounts, dates or promises. Do not mention record IDs. "
             f"Write only the email body (greeting to sign-off), under 130 words, signed '{CFG['business_name']} team'."},
            {"role": "user", "content": f"Recipient: {name}\nFacts:\n{ctx['facts']}\n\nTask: {instruction or ctx['task']}"}]


# ---------------- AI import: map any platform's export into the vault ----------------
FIELDS = ["title", "company", "person", "status", "amount", "due_date", "email", "phone", "summary"]
ENTITIES = ["company", "contact", "deal", "project", "task", "invoice", "lead", "employee", "note"]
HINTS = {"title": ["title", "subject", "name", "task", "deal", "project", "invoice"], "company": ["company", "organization", "organisation", "account", "client", "customer"],
         "person": ["owner", "assignee", "assigned", "rep", "manager"], "status": ["status", "stage", "state"],
         "amount": ["amount", "total", "value", "price", "balance"], "due_date": ["due", "deadline", "close", "end"],
         "email": ["email", "e-mail"], "phone": ["phone", "mobile", "tel"], "summary": ["description", "notes", "note", "details", "comment"]}


def heuristic_mapping(headers: list[str]) -> dict:
    """Header-name rules: tries each hint in priority order, skipping ID columns."""
    m, used = {}, set()
    usable = [h for h in headers if not h.lower().rstrip().endswith("id")]
    for f in FIELDS:
        for w in HINTS[f]:
            h = next((h for h in usable if h not in used and w in h.lower()), None)
            if h:
                m[f] = h
                used.add(h)
                break
    hl = " ".join(headers).lower()
    entity = ("invoice" if "invoice" in hl else "deal" if ("deal" in hl or "stage" in hl) else "task" if ("task" in hl or "assignee" in hl)
              else "contact" if "email" in hl else "record")
    return {"entity": entity, "map": m}


def propose_mapping(headers: list[str], samples: list[dict]) -> dict:
    """Asks the LOCAL model how this unknown export's columns map onto the vault. Falls back to header rules."""
    fallback = heuristic_mapping(headers)
    try:
        out = llm.chat_json([
            {"role": "system", "content": "You map spreadsheet columns exported from business software onto a standard schema. "
             f"Reply with JSON only: {{\"entity\": one of {ENTITIES}, \"map\": {{field: column}}}}. "
             f"Fields: {FIELDS}. Use only column names that exist. Omit fields with no matching column."},
            {"role": "user", "content": f"Columns: {headers}\nSample rows: {json.dumps(samples[:3], ensure_ascii=False)[:1500]}"}])
        ent = out.get("entity") if out.get("entity") in ENTITIES else fallback["entity"]
        mp = {k: v for k, v in (out.get("map") or {}).items() if k in FIELDS and v in headers}
        for k, v in fallback["map"].items():  # fill gaps the model missed
            if k not in mp and v not in mp.values():
                mp[k] = v
        if "title" not in mp:
            return {**fallback, "by": "rules"}
        return {"entity": ent, "map": mp, "by": "local AI"}
    except llm.OllamaError:
        return {**fallback, "by": "rules"}


def import_rows(c, filename: str, entity: str, mapping: dict, rows: list[dict]) -> dict:
    source = f"import:{filename}"
    counts = {"created": 0, "updated": 0, "same": 0}
    t = vault.now()
    for i, row in enumerate(rows):
        get = lambda f: (str(row.get(mapping[f], "")).strip() or None) if f in mapping else None
        title = get("title") or f"Row {i + 1}"
        amount = None
        if get("amount"):
            try:
                amount = float(re.sub(r"[^0-9.\-]", "", get("amount")))
            except ValueError:
                pass
        due = get("due_date")
        if due:
            m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", due) or None
            due = f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else due
        extras = "; ".join(f"{k}: {v}" for k, v in row.items() if v not in (None, "") and k not in mapping.values())
        norm = dict(title=title, company=get("company"), person=get("person"), status=(get("status") or "").lower() or None,
                    amount=amount, due_date=due, email=get("email"), phone=get("phone"),
                    summary=" ".join(x for x in [get("summary"), extras and f"Other fields: {extras}."] if x))
        if entity == "invoice" and norm["status"] not in ("paid",):
            norm["status"] = "paid" if norm["status"] in ("closed", "settled") else "unpaid"
        counts[vault.upsert(c, source, str(row.get("id") or row.get("ID") or i + 1), entity, norm, row, t)] += 1
    c.commit()
    vault.set_meta(c, "index_stale", "1")
    return counts

"""Connectors: pull each platform's records over its API and map them into the vault's common shape.

In demo mode the base URL points at this app's simulated platforms (/mock/...), which use the real
APIs' paths and JSON. Pointing base_url at the real service plus an auth header is how a live
connection would work (see README)."""
from datetime import datetime, timezone

import httpx

from .config import CFG


class Unreachable(Exception):
    """The platform could not be reached (outage, shutdown or no internet)."""
    def __init__(self, state: str, message: str):
        super().__init__(message)
        self.state, self.message = state, message


def base_url(source: str) -> str:
    return f"http://127.0.0.1:{CFG['port']}/mock/{source}"


def _get(c: httpx.Client, url: str, **params):
    try:
        r = c.get(url, params=params)
    except httpx.TransportError as e:
        raise Unreachable("outage", f"Can't reach the server ({e.__class__.__name__}).")
    if r.status_code == 410:
        raise Unreachable("shutdown", r.json().get("message", "Service discontinued."))
    if r.status_code >= 500:
        raise Unreachable("outage", r.json().get("message", f"Server error {r.status_code}."))
    r.raise_for_status()
    return r.json()


def client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(15, connect=3), trust_env=False)


money = lambda v: f"AUD {float(v or 0):,.0f}"


# ---------------- Zoho CRM ----------------
def zoho_crm(c):
    b = base_url("zoho_crm") + "/crm/v2/"
    out = []
    for module, entity in (("Accounts", "company"), ("Contacts", "contact"), ("Deals", "deal"), ("Notes", "note")):
        page = 1
        while True:
            j = _get(c, b + module, page=page, per_page=200)
            for r in j.get("data", []):
                out.append((entity, r["id"], r, _zoho_crm_norm(entity, r)))
            if not j.get("info", {}).get("more_records"):
                break
            page += 1
    return out


def _zoho_crm_norm(entity, r):
    acc = (r.get("Account_Name") or {}) if isinstance(r.get("Account_Name"), dict) else {}
    if entity == "company":
        return dict(title=r["Account_Name"], company=r["Account_Name"], person=r.get("Owner", {}).get("name"),
                    phone=r.get("Phone"), summary=f"{r.get('Industry')} company in {r.get('Billing_City')}, "
                    f"{r.get('Billing_Country')}. Website {r.get('Website')}. Account owner: {r.get('Owner', {}).get('name')}. "
                    f"{r.get('Description', '')}", data={"industry": r.get("Industry"), "country": r.get("Billing_Country")})
    if entity == "contact":
        name = f"{r.get('First_Name', '')} {r.get('Last_Name', '')}".strip()
        return dict(title=name, company=acc.get("name"), person=name, email=r.get("Email"), phone=r.get("Phone"),
                    summary=f"{r.get('Title')} at {acc.get('name')}. Email {r.get('Email')}, phone {r.get('Phone')}.")
    if entity == "deal":
        return dict(title=r["Deal_Name"], company=acc.get("name"), person=r.get("Owner", {}).get("name"),
                    status=r.get("Stage"), amount=r.get("Amount"), due_date=r.get("Closing_Date"),
                    summary=f"Deal owner: {r.get('Owner', {}).get('name')}.")
    parent = (r.get("Parent_Id") or {}).get("name")
    return dict(title=r.get("Note_Title") or "Note", company=parent, summary=r.get("Note_Content", ""),
                due_date=(r.get("Created_Time") or "")[:10], data={"created": r.get("Created_Time")})


# ---------------- Zoho Projects ----------------
def zoho_projects(c):
    b = base_url("zoho_projects") + "/restapi/portal/webinnovationexperts/projects/"
    out = []
    for p in _get(c, b).get("projects", []):
        out.append(("project", p["id"], p, dict(
            title=p["name"], company=p.get("client"), person=p.get("owner_name"), status=p.get("status"),
            due_date=p.get("end_date"), summary=f"Client project for {p.get('client')}, managed by {p.get('owner_name')}, started {p.get('start_date')}.",
            data={"project_id": p["id"]})))
        for t in _get(c, b + p["id"] + "/tasks/").get("tasks", []):
            owners = ", ".join(o["name"] for o in t.get("details", {}).get("owners", []))
            t = dict(t, project_id=p["id"], project_name=p["name"])
            out.append(("task", t["id"], t, dict(
                title=t["name"], company=p.get("client"), person=owners, status=t["status"]["name"],
                due_date=t.get("end_date"), summary=f"Task in project '{p['name']}' ({p.get('client')}), priority {t.get('priority')}.",
                data={"project_id": p["id"], "project": p["name"], "priority": t.get("priority")})))
    return out


# ---------------- Zoho Books ----------------
def zoho_books(c):
    out, page = [], 1
    while True:
        j = _get(c, base_url("zoho_books") + "/api/v3/invoices", page=page, per_page=200)
        for i in j.get("invoices", []):
            out.append(("invoice", i["invoice_id"], i, dict(
                preferred_uid=i["invoice_number"], title=f"Invoice to {i['customer_name']}",
                company=i["customer_name"], status="paid" if i["status"] == "paid" else "unpaid",
                amount=i["total"], due_date=i["due_date"],
                summary=f"Invoice to {i['customer_name']} for {money(i['total'])}, balance {money(i['balance'])}, "
                        f"issued {i['date']}, due {i['due_date']}.", data={"issued": i["date"], "balance": i["balance"]})))
        if not j.get("page_context", {}).get("has_more_page"):
            break
        page += 1
    return out


# ---------------- HubSpot ----------------
def hubspot(c):
    out, after = [], 0
    while True:
        j = _get(c, base_url("hubspot") + "/crm/v3/objects/contacts", limit=100, after=after)
        for r in j.get("results", []):
            p = r["properties"]
            name = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip()
            out.append(("lead", r["id"], r, dict(
                title=f"{name} ({p.get('company')})", company=p.get("company"), person=p.get("hubspot_owner"),
                status=p.get("lifecyclestage"), email=p.get("email"),
                summary=f"Lead {name} from {p.get('company')}, lifecycle stage {p.get('lifecyclestage')}, "
                        f"owner {p.get('hubspot_owner')}. Message: {p.get('message')}")))
        nxt = j.get("paging", {}).get("next", {}).get("after")
        if not nxt:
            break
        after = int(nxt)
    return out


# ---------------- ClickUp ----------------
def clickup(c):
    out = []
    for t in _get(c, base_url("clickup") + "/api/v2/team/webinnovationexperts/task", page=0).get("tasks", []):
        who = ", ".join(a["username"] for a in t.get("assignees", []))
        due = datetime.fromtimestamp(int(t["due_date"]) / 1000, tz=timezone.utc).date().isoformat() if t.get("due_date") else None
        tags = ", ".join(x["name"] for x in t.get("tags", []))
        out.append(("task", t["id"], t, dict(
            title=t["name"], company="Web Innovation Experts (internal)", person=who, status=t["status"]["status"],
            due_date=due, summary=f"Internal task in ClickUp list {t['list']['name']}. Tags: {tags}.",
            data={"list": t["list"]["name"], "tags": tags})))
    return out


# ---------------- BambooHR ----------------
def bamboohr(c):
    out = []
    for e in _get(c, base_url("bamboohr") + "/api/gateway.php/webinnovationexperts/v1/employees/directory").get("employees", []):
        out.append(("employee", e["id"], e, dict(
            title=e["displayName"], company="Web Innovation Experts (internal)", person=e["displayName"], status="active",
            email=e.get("workEmail"), phone=e.get("mobilePhone"),
            summary=f"Employee: {e['jobTitle']} in {e['department']}, based in {e['location']}. "
                    f"Email {e.get('workEmail')}, mobile {e.get('mobilePhone')}. Hired {e.get('hireDate')}.",
            data={"department": e["department"], "job_title": e["jobTitle"]})))
    return out


CONNECTORS = {
    "zoho_crm": ("Zoho CRM", "Companies, contacts, deals, notes", zoho_crm),
    "zoho_projects": ("Zoho Projects", "Projects and tasks", zoho_projects),
    "zoho_books": ("Zoho Books", "Invoices", zoho_books),
    "hubspot": ("HubSpot", "Marketing leads", hubspot),
    "clickup": ("ClickUp", "Internal sprint tasks", clickup),
    "bamboohr": ("BambooHR", "Employees (HR)", bamboohr),
}


# ---------------- write-back (changes made while a platform was down) ----------------
def push_change(ch: dict, rec: dict | None):
    """Sends one queued local change back to its platform. Raises Unreachable if still down."""
    import json
    payload = json.loads(ch["payload"])
    with client() as c:
        if ch["kind"] == "task_status" and rec and rec["source"] == "zoho_projects":
            pid = json.loads(rec["data"])["project_id"]
            r = c.post(base_url("zoho_projects") + f"/restapi/portal/webinnovationexperts/projects/{pid}/tasks/{rec['source_id']}/",
                       json={"status": payload["status"]})
        elif ch["kind"] == "task_status" and rec and rec["source"] == "clickup":
            r = c.put(base_url("clickup") + f"/api/v2/task/{rec['source_id']}", json={"status": payload["status"]})
        elif ch["kind"] == "note":
            r = c.post(base_url("zoho_crm") + "/crm/v2/Notes", json={"data": [{
                "Note_Title": payload["title"], "Note_Content": payload["content"],
                "Parent_Id": {"name": payload["company"], "id": payload.get("company_source_id")}}]})
        else:
            raise ValueError(f"Unsupported change: {ch['kind']}")
    if r.status_code == 410:
        raise Unreachable("shutdown", "Platform discontinued.")
    if r.status_code >= 500:
        raise Unreachable("outage", "Platform still down.")
    r.raise_for_status()

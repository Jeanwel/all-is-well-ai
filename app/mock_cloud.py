"""Simulated third-party platforms for the demo, served at /mock/<platform>/...

Each one answers on the same URL paths and in the same JSON shapes as the real API
(Zoho CRM v2, Zoho Projects REST, Zoho Books v3, HubSpot CRM v3, ClickUp v2, BambooHR),
so the connectors are written against real formats. Each platform can be switched to:
  up        normal
  down      outage (HTTP 503), like a regional cloud incident
  shutdown  service discontinued (HTTP 410), like a vendor closing or locking you out"""
import copy
import random
import threading
from datetime import date, datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import demo_data

PLATFORMS = {
    "zoho_crm": "Zoho CRM", "zoho_projects": "Zoho Projects", "zoho_books": "Zoho Books",
    "hubspot": "HubSpot", "clickup": "ClickUp", "bamboohr": "BambooHR",
}
router = APIRouter(prefix="/mock")
_lock = threading.Lock()
STATE = {"day": None, "data": {}, "status": {p: "up" for p in PLATFORMS}, "activity": 0}


def data() -> dict:
    with _lock:
        if STATE["day"] != date.today():
            STATE["data"] = demo_data.generate()
            STATE["day"] = date.today()
        return STATE["data"]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def gate(platform: str):
    s = STATE["status"][platform]
    if s == "down":
        return JSONResponse({"code": "SERVICE_UNAVAILABLE", "message": f"{PLATFORMS[platform]} is experiencing an outage."}, 503)
    if s == "shutdown":
        return JSONResponse({"code": "GONE", "message": f"{PLATFORMS[platform]} has been discontinued for this account."}, 410)
    return None


def paginate(items, page_no, per_page):
    start = (page_no - 1) * per_page
    return items[start:start + per_page], start + per_page < len(items)


# ---------------- Zoho CRM v2 ----------------
@router.get("/zoho_crm/crm/v2/{module}")
def zoho_crm(module: str, page_no: int = 1, per_page: int = 200, page: int | None = None):
    if r := gate("zoho_crm"):
        return r
    items = data()["zoho_crm"].get(module)
    if items is None:
        return JSONResponse({"code": "INVALID_MODULE"}, 400)
    rows, more = paginate(items, page or page_no, per_page)
    return {"data": rows, "info": {"per_page": per_page, "page": page or page_no, "more_records": more, "count": len(rows)}}


@router.post("/zoho_crm/crm/v2/Notes")
async def zoho_crm_add_note(req: Request):
    if r := gate("zoho_crm"):
        return r
    body = await req.json()
    out = []
    for n in body.get("data", []):
        rec = {"id": "4876876000099" + str(random.randint(10000, 99999)), "Note_Title": n.get("Note_Title", ""),
               "Note_Content": n.get("Note_Content", ""), "Parent_Id": n.get("Parent_Id"), "se_module": "Accounts",
               "Created_Time": now_iso()}
        data()["zoho_crm"]["Notes"].append(rec)
        out.append({"code": "SUCCESS", "details": {"id": rec["id"]}})
    return {"data": out}


# ---------------- Zoho Projects ----------------
@router.get("/zoho_projects/restapi/portal/{portal}/projects/")
def zp_projects(portal: str):
    if r := gate("zoho_projects"):
        return r
    return {"projects": data()["zoho_projects"]["projects"]}


@router.get("/zoho_projects/restapi/portal/{portal}/projects/{pid}/tasks/")
def zp_tasks(portal: str, pid: str):
    if r := gate("zoho_projects"):
        return r
    return {"tasks": data()["zoho_projects"]["tasks"].get(pid, [])}


@router.post("/zoho_projects/restapi/portal/{portal}/projects/{pid}/tasks/{tid}/")
async def zp_update_task(portal: str, pid: str, tid: str, req: Request):
    if r := gate("zoho_projects"):
        return r
    body = await req.json()
    for t in data()["zoho_projects"]["tasks"].get(pid, []):
        if t["id"] == tid:
            if "status" in body:
                t["status"] = {"name": body["status"]}
            t["last_updated_time"] = now_iso()
            return {"tasks": [t]}
    return JSONResponse({"error": "task not found"}, 404)


# ---------------- Zoho Books v3 ----------------
@router.get("/zoho_books/api/v3/invoices")
def zb_invoices(page: int = 1, per_page: int = 200):
    if r := gate("zoho_books"):
        return r
    rows, more = paginate(data()["zoho_books"]["invoices"], page, per_page)
    return {"code": 0, "invoices": rows, "page_context": {"page": page, "has_more_page": more}}


# ---------------- HubSpot CRM v3 ----------------
@router.get("/hubspot/crm/v3/objects/contacts")
def hs_contacts(limit: int = 100, after: int = 0):
    if r := gate("hubspot"):
        return r
    items = data()["hubspot"]["contacts"]
    rows = items[after:after + limit]
    out = {"results": rows}
    if after + limit < len(items):
        out["paging"] = {"next": {"after": str(after + limit)}}
    return out


# ---------------- ClickUp v2 ----------------
@router.get("/clickup/api/v2/team/{team}/task")
def cu_tasks(team: str, page: int = 0):
    if r := gate("clickup"):
        return r
    return {"tasks": data()["clickup"]["tasks"] if page == 0 else [], "last_page": True}


@router.put("/clickup/api/v2/task/{tid}")
async def cu_update(tid: str, req: Request):
    if r := gate("clickup"):
        return r
    body = await req.json()
    for t in data()["clickup"]["tasks"]:
        if t["id"] == tid:
            if "status" in body:
                t["status"] = {"status": body["status"]}
            t["date_updated"] = str(int(datetime.now().timestamp() * 1000))
            return t
    return JSONResponse({"err": "Task not found"}, 404)


# ---------------- BambooHR ----------------
@router.get("/bamboohr/api/gateway.php/{company}/v1/employees/directory")
def bamboo(company: str):
    if r := gate("bamboohr"):
        return r
    return {"employees": data()["bamboohr"]["employees"]}


# ---------------- demo controls ----------------
def set_status(platform: str, status: str):
    STATE["status"][platform] = status


def simulate_activity() -> str:
    """Makes a realistic change in the 'cloud' so the next sync shows a new version."""
    d = data()
    STATE["activity"] += 1
    n = STATE["activity"] % 3
    if n == 1:
        inv = next((i for i in d["zoho_books"]["invoices"] if i["status"] == "overdue"), None)
        if inv:
            inv.update(status="paid", balance=0, last_modified_time=now_iso())
            return f"{inv['customer_name']} paid {inv['invoice_number']} in Zoho Books."
    if n == 2:
        deal = next((x for x in d["zoho_crm"]["Deals"] if x["Stage"] == "Negotiation/Review"), None)
        if deal:
            deal.update(Stage="Closed Won", Modified_Time=now_iso())
            return f"Deal '{deal['Deal_Name']}' was marked Closed Won in Zoho CRM."
    acc = d["zoho_crm"]["Accounts"][0]
    d["zoho_crm"]["Notes"].append({"id": "4876876000088" + str(random.randint(10000, 99999)), "Note_Title": "Call summary",
                                   "Note_Content": f"Spoke with {acc['Account_Name']}: they approved the homepage design and want launch moved forward by two days.",
                                   "Parent_Id": {"name": acc["Account_Name"], "id": acc["id"]}, "se_module": "Accounts",
                                   "Created_Time": now_iso()})
    return f"A new call note was added to {acc['Account_Name']} in Zoho CRM."


def reset():
    with _lock:
        STATE["day"] = None
        STATE["status"] = {p: "up" for p in PLATFORMS}
    data()
    return copy.deepcopy(STATE["status"])

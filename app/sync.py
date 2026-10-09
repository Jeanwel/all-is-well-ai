"""Sync agent: runs in the background, keeps the vault up to date, detects outages, and pushes
changes made locally back to each platform once it is reachable again."""
import json
import socket
import threading

import httpx

from . import connectors, vault
from .config import CFG, DATA_LOG

_sync_lock = threading.Lock()


class Net:
    """Internet state. 'simulated' is the stage backup for turning Wi-Fi off."""
    real_ok = True
    simulated = False

    @classmethod
    def online(cls):
        return cls.real_ok and not cls.simulated


def check_internet() -> bool:
    try:
        if httpx.get(CFG["connectivity_url"], timeout=2.0).status_code < 500:
            return True
    except Exception:
        pass
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            socket.create_connection((host, port), timeout=1.5).close()
            return True
        except OSError:
            continue
    return False


def _set_conn(c, source, state, error=None, success=False):
    name = connectors.CONNECTORS[source][0] if source in connectors.CONNECTORS else source
    t = vault.now()
    c.execute("INSERT INTO connections(source,name,state,last_attempt_at,last_error) VALUES(?,?,?,?,?) "
              "ON CONFLICT(source) DO UPDATE SET state=excluded.state, last_attempt_at=excluded.last_attempt_at, "
              "last_error=excluded.last_error", (source, name, state, t, error))
    if success:
        c.execute("UPDATE connections SET last_success_at=? WHERE source=?", (t, source))
    c.commit()


def sync_source(c, source: str) -> dict:
    """Pulls one platform into the vault. Never deletes local copies, even if the platform is gone."""
    started = vault.now()
    if not Net.online():
        _set_conn(c, source, "offline", "No internet connection.")
        res = {"source": source, "status": "offline", "message": "No internet connection; using the local vault."}
    else:
        try:
            with connectors.client() as hc:
                items = connectors.CONNECTORS[source][2](hc)
            counts = {"created": 0, "updated": 0, "same": 0}
            for entity, sid, raw, norm in items:
                counts[vault.upsert(c, source, sid, entity, norm, raw, started)] += 1
            c.commit()
            _set_conn(c, source, "connected", None, success=True)
            res = {"source": source, "status": "ok", "fetched": len(items), **counts,
                   "message": f"{len(items)} records checked: {counts['created']} new, {counts['updated']} changed."}
        except connectors.Unreachable as e:
            _set_conn(c, source, e.state, e.message)
            res = {"source": source, "status": e.state, "message": e.message}
        except Exception as e:
            _set_conn(c, source, "error", str(e)[:300])
            res = {"source": source, "status": "error", "message": str(e)[:300]}
    c.execute("INSERT INTO sync_runs(source,started_at,finished_at,status,message,fetched,created,updated) "
              "VALUES (?,?,?,?,?,?,?,?)", (source, started, vault.now(), res["status"], res["message"],
                                          res.get("fetched", 0), res.get("created", 0), res.get("updated", 0)))
    c.commit()
    return res


def sync_all(c=None) -> list[dict]:
    own = c is None
    c = c or vault.connect()
    with _sync_lock:
        out = [sync_source(c, s) for s in connectors.CONNECTORS]
    if any(r.get("created") or r.get("updated") for r in out):
        vault.set_meta(c, "index_stale", "1")
    if own:
        c.close()
    return out


# ---------------- local changes queue ----------------
def queue_change(c, kind: str, source: str, uid: str | None, payload: dict, description: str) -> dict:
    cur = c.execute("INSERT INTO changes(kind,source,uid,payload,description,status,created_at) VALUES (?,?,?,?,?,?,?)",
                    (kind, source, uid, json.dumps(payload), description, "Queued", vault.now()))
    c.commit()
    push_changes(c)
    return vault.rows(c.execute("SELECT * FROM changes WHERE id=?", (cur.lastrowid,)))[0]


def push_changes(c=None) -> int:
    """Tries to send every queued change. Emails need only internet; others need their platform up."""
    own = c is None
    c = c or vault.connect()
    pushed = 0
    for ch in vault.rows(c.execute("SELECT * FROM changes WHERE status='Queued' ORDER BY id")):
        if not Net.online():
            break
        try:
            if ch["kind"] == "email":
                p = json.loads(ch["payload"])
                with open(DATA_LOG, "a", encoding="utf-8") as f:
                    f.write(f"{vault.now()}\tSIMULATED EMAIL\tto={p['to']}\tsubject={p['subject']}\n")
            else:
                rec = c.execute("SELECT * FROM records WHERE uid=?", (ch["uid"],)).fetchone() if ch["uid"] else None
                connectors.push_change(ch, dict(rec) if rec else None)
            c.execute("UPDATE changes SET status='Pushed', pushed_at=?, error=NULL WHERE id=?", (vault.now(), ch["id"]))
            c.commit()
            pushed += 1
        except (connectors.Unreachable, httpx.TransportError):
            continue  # platform still down; try again later
        except Exception as e:
            c.execute("UPDATE changes SET status='Failed', error=? WHERE id=?", (str(e)[:300], ch["id"]))
            c.commit()
    if pushed:
        sources = {r[0] for r in c.execute("SELECT DISTINCT source FROM changes WHERE status='Pushed' AND source!='email'")}
        with _sync_lock:
            for s in sources & set(connectors.CONNECTORS):
                sync_source(c, s)
        vault.set_meta(c, "index_stale", "1")
    if own:
        c.close()
    return pushed

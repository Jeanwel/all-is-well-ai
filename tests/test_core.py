"""Core tests: sync into the vault, outages/shutdowns, retrieval, the report's SQL, the write-back queue,
AI import and export. Run:  python -m pytest -q   (no Ollama or network needed)."""
import contextlib
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import config, connectors, llm, mock_cloud, sync, vault
    from tests.fake_ollama import hash_embed
    monkeypatch.setattr(vault, "DB_PATH", tmp_path / "vault.db")
    monkeypatch.setattr(vault, "VAULT_DIR", tmp_path)
    monkeypatch.setattr(sync, "DATA_LOG", tmp_path / "sent.log")
    monkeypatch.setattr(llm, "embed", lambda texts, kind="document": np.asarray([hash_embed(t) for t in texts], dtype=np.float32))
    from app.main import app
    tc = TestClient(app)  # no "with": the background agent doesn't start
    monkeypatch.setattr(connectors, "client", lambda: contextlib.nullcontext(tc))
    sync.Net.real_ok, sync.Net.simulated = True, False
    mock_cloud.reset()
    c = vault.connect(tmp_path / "vault.db")
    yield c, tc


def test_sync_copies_every_platform(env):
    c, _ = env
    from app import sync, vault
    res = sync.sync_all(c)
    assert all(r["status"] == "ok" for r in res)
    st = vault.stats(c)
    assert st["by_source"] == {"zoho_crm": 74, "zoho_projects": 54, "zoho_books": 30, "hubspot": 12, "clickup": 16, "bamboohr": 12}
    assert c.execute("SELECT COUNT(*) FROM records WHERE raw IS NULL OR last_synced_at IS NULL").fetchone()[0] == 0
    # second sync: nothing new, nothing changed
    again = sync.sync_all(c)
    assert sum(r["created"] + r["updated"] for r in again) == 0


def test_outage_and_shutdown_keep_the_data(env):
    c, _ = env
    from app import mock_cloud, sync, vault
    sync.sync_all(c)
    mock_cloud.set_status("zoho_books", "shutdown")
    mock_cloud.set_status("zoho_crm", "down")
    res = {r["source"]: r["status"] for r in sync.sync_all(c)}
    assert res["zoho_books"] == "shutdown" and res["zoho_crm"] == "outage" and res["hubspot"] == "ok"
    assert vault.stats(c)["by_source"]["zoho_books"] == 30  # nothing lost
    sync.Net.simulated = True
    assert all(r["status"] == "offline" for r in sync.sync_all(c))


def test_retrieval_and_exact_lookups(env):
    c, _ = env
    from app import ai, sync
    sync.sync_all(c)
    ai.ensure_index(c)
    facts = ai.facts_for(c, "Why hasn't Thames Fintech paid?")
    uids = [u for u, _ in facts]
    assert "INV-2042" in uids
    assert any("PO-88213" in t for _, t in facts)            # the CRM note explaining the blocked invoice
    assert any("AUD 38,000" in t and "EXACT LOOKUP" in t for _, t in facts)
    people = ai.facts_for(c, "What is Migs working on this week?")
    assert any("Migs Cruz" in t for _, t in people)


def test_report_sql(env):
    c, _ = env
    from app import ai, sync
    sync.sync_all(c)
    f = ai.report_facts(c)
    assert f["overdue_total"] == sum(r["amount"] for r in f["overdue"]) == 104800
    assert "INV-2042" in [r["uid"] for r in f["overdue"]]
    assert any("property listings" in r["title"] for r in f["tasks_today"])
    assert all(r["due_date"] < f["date"] for r in f["tasks_late"])
    assert len(f["connections"]) == 6


def test_changes_queue_while_down_and_push_when_back(env):
    c, tc = env
    from app import mock_cloud, sync, vault
    sync.sync_all(c)
    uid = c.execute("SELECT uid FROM records WHERE title LIKE '%property listings%'").fetchone()[0]
    mock_cloud.set_status("zoho_projects", "down")
    r = tc.post("/api/changes/task-status", json={"uid": uid, "status": "done"}).json()
    assert r["status"] == "Queued"
    assert vault.find(c, "uid=?", (uid,))[0]["status"] == "Closed"     # usable locally right away
    mock_cloud.set_status("zoho_projects", "up")
    assert sync.push_changes(c) == 1
    rec = vault.find(c, "uid=?", (uid,))[0]
    assert rec["status"] == "Closed" and rec["version"] == 2 and rec["local_edit"] == 0


def test_ai_import_and_export(env):
    c, _ = env
    from app import ai, sync, vault
    sync.sync_all(c)
    import csv
    text = (ROOT / "web/samples/pipedrive-deals-export.csv").read_text()
    rows = list(csv.DictReader(io.StringIO(text)))
    m = ai.heuristic_mapping(list(rows[0].keys()))
    assert m["entity"] == "deal" and m["map"]["title"] == "Deal - Title" and m["map"]["amount"] == "Deal - Value"
    assert ai.import_rows(c, "pipedrive.csv", "deal", m["map"], rows)["created"] == 6
    assert vault.find(c, "source='import:pipedrive.csv' AND amount=16800")
    name, data = vault.export_zip(c)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "csv/invoices.csv" in names and "original_json/zoho_crm.json" in names and "README.txt" in names

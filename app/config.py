"""Settings. Edit config.json, or create config.local.json (setup writes the model choice there)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = Path(os.environ.get("AIW_VAULT_DIR", ROOT / "vault"))   # everything the agent keeps, on this computer
DB_PATH = VAULT_DIR / "vault.db"
DATA_LOG = VAULT_DIR / "sent_log.txt"   # simulated outgoing email log
WEB_DIR = ROOT / "web"

DEFAULTS = {
    "business_name": "Northstar Digital",
    "llm_model": "llama3.2:3b",
    "embed_model": "nomic-embed-text",
    "ollama_host": "http://127.0.0.1:11434",
    "port": 8000,
    "auto_sync_seconds": 60,
    "connectivity_url": "http://connectivitycheck.gstatic.com/generate_204",
    "num_ctx": 4096,
    "top_k": 6,
}


def _normalize_host(h: str) -> str:
    h = h.strip().rstrip("/")
    if not h.startswith("http"):
        h = "http://" + h
    h = h.replace("0.0.0.0", "127.0.0.1")
    if h.count(":") < 2:
        h += ":11434"
    return h


def load() -> dict:
    cfg = dict(DEFAULTS)
    for name in ("config.json", "config.local.json"):
        p = ROOT / name
        if p.exists():
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
    env = {"llm_model": "AIW_LLM_MODEL", "embed_model": "AIW_EMBED_MODEL", "ollama_host": "OLLAMA_HOST",
           "port": "AIW_PORT", "connectivity_url": "AIW_CONNECTIVITY_URL"}
    for key, var in env.items():
        if os.environ.get(var):
            cfg[key] = os.environ[var]
    cfg["ollama_host"] = _normalize_host(str(cfg["ollama_host"]))
    cfg["port"] = int(cfg["port"])
    return cfg


CFG = load()

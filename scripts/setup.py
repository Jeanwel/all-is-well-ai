"""One-command setup:  python scripts/setup.py

Creates .venv, installs pinned dependencies, checks this computer and picks a model size, starts Ollama,
downloads the models, runs a first sync of every platform into the local vault, builds the AI index,
and puts a start-demo launcher on the Desktop. Safe to run again."""
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def step(msg):
    print(f"\n==> {msg}", flush=True)


def bootstrap():
    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11+ is required (you have {sys.version.split()[0]}). Install it from python.org and re-run.")
    if not PY.exists():
        step("Creating virtual environment (.venv)")
        venv.create(VENV, with_pip=True)
    step("Installing Python dependencies (pinned in requirements.txt)")
    subprocess.check_call([str(PY), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")])
    sys.exit(subprocess.call([str(PY), str(Path(__file__)), "--in-venv"] + sys.argv[1:], cwd=ROOT))


def first_sync():
    """Starts the app briefly in the background, syncs every platform into the vault, builds the index."""
    import socket
    import threading
    import time

    import uvicorn
    from app import ai, sync, vault
    from app.config import CFG
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        CFG["port"] = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=CFG["port"], log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.1)
    c = vault.connect()
    for r in sync.sync_all(c):
        print(f"   {r['source']:<14} {r['message']}")
    n = ai.ensure_index(c)
    print(f"   {n} records embedded locally for AI search")
    server.should_exit = True
    time.sleep(0.5)


def main():
    sys.path.insert(0, str(ROOT))
    import json
    from app import llm, ollama_setup as ol
    from app.config import CFG, load

    step("Checking this computer")
    hw = ol.hardware()
    print(f"   OS: {hw['os']}   RAM: {hw['ram_gb']} GB   GPU: {hw['gpu']}")
    local_cfg = ROOT / "config.local.json"
    if not local_cfg.exists() and not os.environ.get("AIW_LLM_MODEL"):
        CFG["llm_model"] = ol.pick_model(hw["ram_gb"])
        local_cfg.write_text(json.dumps({"llm_model": CFG["llm_model"]}, indent=2))
    print(f"   Using LLM: {CFG['llm_model']}   embeddings: {CFG['embed_model']}  (change in config.local.json)")

    step("Starting Ollama (the local AI engine)")
    if not ol.start():
        print("""
   Ollama didn't respond. Usually it's one of these:
     1. Windows: open "Ollama" from the Start menu once (a llama icon appears by the clock),
        or close this window, open a NEW PowerShell and run setup again.
     2. Not installed yet: https://ollama.com/download  (Windows: winget install -e --id Ollama.Ollama)
     3. Check it: open http://localhost:11434 in a browser. It should say "Ollama is running".
   Then run this setup again.
""")
        sys.exit(1)
    print("   Ollama is running at", CFG["ollama_host"])

    step("Downloading AI models (one time, about 2.3 GB; needs internet)")
    have = llm.list_models()
    for m in (CFG["llm_model"], CFG["embed_model"]):
        if llm.has_model(m, have):
            print(f"   {m}: already downloaded")
        else:
            ol.pull(m)

    step("Testing both models")
    v = llm.embed(["hello"], kind="query")
    print(f"   embeddings OK ({v.shape[1]} dimensions)")
    reply = "".join(llm.chat_stream([{"role": "user", "content": "Say: All is well."}], max_tokens=12)).strip()
    print(f"   LLM OK, it says: {reply!r}")

    step("First sync: copying every platform into the local vault")
    first_sync()

    if "--no-desktop" not in sys.argv:
        step("Creating the Desktop launcher")
        from scripts.make_launcher import make
        print("  ", make())

    print(f"\nAll set. Start the app with:\n\n    python run.py\n\nthen open http://localhost:{load()['port']}\n")


if __name__ == "__main__":
    if "--in-venv" in sys.argv:
        main()
    else:
        bootstrap()

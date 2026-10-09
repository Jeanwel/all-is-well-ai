"""Start All Is Well AI:  python run.py   (opens http://localhost:8000)

Starts Ollama if needed, warms up the local model, starts the agent (which syncs every platform into
the local vault), and opens the browser. Options: --no-browser"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

# Re-launch inside the project's virtual environment if we're not already in it.
if VENV_PY.exists() and Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
    sys.exit(subprocess.call([str(VENV_PY), str(ROOT / "run.py")] + sys.argv[1:]))

try:
    import uvicorn
except ImportError:
    sys.exit("Dependencies are missing. Run the setup first:  python scripts/setup.py")

sys.path.insert(0, str(ROOT))
from app import llm, ollama_setup  # noqa: E402
from app.config import CFG  # noqa: E402


def free_port(start):
    for p in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def main():
    print("All Is Well AI: your business brain, on your own computer\n")
    print("-> Checking the local AI (Ollama)...")
    if ollama_setup.start():
        print("   Ollama is running.")
    else:
        print("   !! Ollama isn't running and couldn't be started. Open the Ollama app (or run `ollama serve`).\n"
              "      The app still opens and the vault still works; AI answers start as soon as Ollama is up.")

    def warm():
        try:
            t = time.time()
            llm.warmup()
            print(f"-> Model {CFG['llm_model']} warmed up in {time.time() - t:.1f}s. Ready for questions.")
        except llm.OllamaError as e:
            print("   !! Warm-up skipped:", e.message, e.fix)
    threading.Thread(target=warm, daemon=True).start()

    port = free_port(CFG["port"])
    if port != CFG["port"]:
        print(f"   Port {CFG['port']} is busy, using {port} instead.")
        CFG["port"] = port
    url = f"http://localhost:{port}"
    print(f"-> Opening {url}   (press Ctrl+C to stop)\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()

"""Helpers shared by setup and run: find/start Ollama, pull models, pick a model size for this machine."""
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from .config import CFG


def reachable() -> bool:
    try:
        return httpx.get(CFG["ollama_host"] + "/api/tags", timeout=2, trust_env=False).status_code == 200
    except Exception:
        return False


def find_binary():
    exe = shutil.which("ollama")
    if exe:
        return exe
    candidates = [Path.home() / "AppData/Local/Programs/Ollama/ollama.exe",
                  Path("/Applications/Ollama.app/Contents/Resources/ollama"), Path("/usr/local/bin/ollama")]
    return next((str(p) for p in candidates if p.exists()), None)


def start(wait=25) -> bool:
    """Start Ollama in the background if it isn't running. Returns True when it answers."""
    if reachable():
        return True
    system = platform.system()
    if system == "Darwin" and Path("/Applications/Ollama.app").exists():
        subprocess.Popen(["open", "-a", "Ollama"])
    else:
        exe = find_binary()
        if not exe:
            return False
        flags = 0x08000000 if system == "Windows" else 0  # CREATE_NO_WINDOW
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags, start_new_session=(system != "Windows"))
    for _ in range(wait * 2):
        if reachable():
            return True
        time.sleep(0.5)
    return False


def pull(model: str):
    """Downloads a model through Ollama's API, printing progress."""
    last = ""
    with httpx.stream("POST", CFG["ollama_host"] + "/api/pull", json={"model": model, "stream": True},
                      timeout=httpx.Timeout(None, connect=5), trust_env=False) as r:
        for line in r.iter_lines():
            if not line:
                continue
            m = json.loads(line)
            if m.get("error"):
                raise RuntimeError(m["error"])
            msg = m.get("status", "")
            if m.get("total") and m.get("completed"):
                msg += f" {m['completed'] * 100 // m['total']}%"
            if msg != last:
                print(f"\r   {model}: {msg:<60}", end="", flush=True)
                last = msg
    print()


def hardware():
    import psutil
    ram_gb = round(psutil.virtual_memory().total / 1024 ** 3)
    gpu = "unknown"
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        gpu = "Apple Silicon (unified memory)"
    elif shutil.which("nvidia-smi"):
        try:
            gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                 capture_output=True, text=True, timeout=5).stdout.strip() or "NVIDIA"
        except Exception:
            gpu = "NVIDIA"
    return {"os": f"{platform.system()} {platform.release()}", "ram_gb": ram_gb, "gpu": gpu}


def pick_model(ram_gb: int) -> str:
    # 3B is the sweet spot for 8-16 GB laptops; drop to 1B on small machines.
    return "llama3.2:3b" if ram_gb >= 8 else "llama3.2:1b"

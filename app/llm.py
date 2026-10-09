"""Thin client for the local Ollama server (LLM + embeddings). Nothing here leaves the laptop."""
import json

import httpx
import numpy as np

from .config import CFG

TIMEOUT = httpx.Timeout(180.0, connect=3.0)


class OllamaError(Exception):
    def __init__(self, message: str, fix: str):
        super().__init__(message)
        self.message, self.fix = message, fix


def _url(path: str) -> str:
    return CFG["ollama_host"] + path


def _not_running() -> OllamaError:
    return OllamaError("Ollama isn't running on this computer.",
                       "Open the Ollama app (or run `ollama serve` in a terminal), then try again.")


def _check(resp: httpx.Response, model: str):
    if resp.status_code == 404:
        raise OllamaError(f"The model '{model}' isn't downloaded yet.", f"Run: ollama pull {model}")
    if resp.status_code >= 400:
        raise OllamaError(f"Ollama returned an error ({resp.status_code}).", resp.text[:300])


def client() -> httpx.Client:
    # trust_env=False: never route local calls through a system proxy
    return httpx.Client(timeout=TIMEOUT, trust_env=False)


def list_models() -> list[str]:
    try:
        with client() as c:
            r = c.get(_url("/api/tags"))
        return [m["name"] for m in r.json().get("models", [])]
    except httpx.TransportError:
        raise _not_running()


def has_model(name: str, models: list[str]) -> bool:
    return any(m == name or m == name + ":latest" or m.split(":")[0] == name for m in models)


def embed(texts: list[str], kind: str = "document") -> np.ndarray:
    """nomic-embed-text expects task prefixes. Returns L2-normalised float32 vectors."""
    prefix = "search_query: " if kind == "query" else "search_document: "
    model = CFG["embed_model"]
    try:
        with client() as c:
            r = c.post(_url("/api/embed"), json={"model": model, "input": [prefix + t for t in texts],
                                                  "keep_alive": "60m"})
    except httpx.TransportError:
        raise _not_running()
    _check(r, model)
    v = np.asarray(r.json()["embeddings"], dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def chat_stream(messages: list[dict], max_tokens: int = 350, temperature: float = 0.2):
    """Yields text pieces as the local model generates them."""
    model = CFG["llm_model"]
    body = {"model": model, "messages": messages, "stream": True, "keep_alive": "60m",
            "options": {"temperature": temperature, "num_ctx": CFG["num_ctx"], "num_predict": max_tokens}}
    try:
        with client() as c, c.stream("POST", _url("/api/chat"), json=body) as r:
            if r.status_code >= 400:
                r.read()
                _check(r, model)
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise OllamaError("The local model reported an error.", msg["error"])
                piece = msg.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if msg.get("done"):
                    break
    except httpx.TransportError:
        raise _not_running()


def warmup():
    """Loads both models into memory so the first question on stage is fast."""
    embed(["warm up"], kind="query")
    for _ in chat_stream([{"role": "user", "content": "Reply with: ready"}], max_tokens=5):
        pass


def chat_json(messages: list[dict], max_tokens: int = 500) -> dict:
    """Asks the local model for a JSON object (Ollama's JSON mode)."""
    model = CFG["llm_model"]
    body = {"model": model, "messages": messages, "stream": False, "format": "json", "keep_alive": "60m",
            "options": {"temperature": 0, "num_ctx": CFG["num_ctx"], "num_predict": max_tokens}}
    try:
        with client() as c:
            r = c.post(_url("/api/chat"), json=body)
    except httpx.TransportError:
        raise _not_running()
    _check(r, model)
    try:
        return json.loads(r.json()["message"]["content"])
    except (ValueError, KeyError):
        return {}

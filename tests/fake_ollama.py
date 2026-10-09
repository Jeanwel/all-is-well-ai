"""A tiny stand-in for Ollama used only by tests/CI (no models needed).
Embeddings are hashed bag-of-words vectors; chat echoes the first cited IDs from the prompt.
Run manually:  python -m uvicorn tests.fake_ollama:app --port 11435"""
import hashlib
import json
import re
import time

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
DIM = 768


def hash_embed(text: str) -> list[float]:
    v = np.zeros(DIM, dtype=np.float32)
    words = re.findall(r"[a-z0-9]+", text.lower().replace("search_query:", "").replace("search_document:", ""))
    for w in words + [a + " " + b for a, b in zip(words, words[1:])]:
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1
    return (v / (np.linalg.norm(v) + 1e-9)).tolist()


def fake_answer(prompt: str) -> str:
    ids = list(dict.fromkeys(re.findall(r"\[([A-Z]{2,3}-\d+)\]", prompt)))[:3]
    if "FACTS:" in prompt:
        return "## Top priorities\n- Follow up on overdue invoices " + " ".join(f"[{i}]" for i in ids) + "\n## Money\n- See totals below.\n"
    if not ids:
        return "Dear client, this is a friendly reminder. Thank you!\nBayanihan Creative Studio"
    return "From your records: " + ", ".join(f"[{i}]" for i in ids) + "."


@app.get("/api/tags")
def tags():
    return {"models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text:latest"}]}


@app.post("/api/embed")
async def embed(req: Request):
    body = await req.json()
    inp = body["input"] if isinstance(body["input"], list) else [body["input"]]
    return {"embeddings": [hash_embed(t) for t in inp]}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    text = fake_answer(" ".join(m["content"] for m in body["messages"]))
    if body.get("format") == "json":
        return {"message": {"content": '{"entity": "deal", "map": {}}'}, "done": True}

    def gen():
        for word in re.split(r"(\s+)", text):
            yield json.dumps({"message": {"content": word}, "done": False}) + "\n"
            time.sleep(0.002)
        yield json.dumps({"message": {"content": ""}, "done": True}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/pull")
async def pull():
    return StreamingResponse(iter([json.dumps({"status": "success"}) + "\n"]), media_type="application/x-ndjson")

import asyncio
import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .services import rules
from .services.ollama import generate, TURN_SCHEMA
from .services.storage import Storage
from .services.tts import piper_command, VOICE_LABELS
from .services.knowledge import Knowledge
from .services.topics import TopicPools
from .services.rounds import Rounds

app = FastAPI(title="AI Bingo Party — local API")
storage = Storage()
knowledge = Knowledge(storage)
topic_pools = TopicPools(storage, knowledge)
rounds = Rounds(storage, knowledge)


class Request(BaseModel):
    settings: dict = Field(default_factory=dict)
    state: dict = Field(default_factory=dict)
    topic: str = ""
    category: str = "Characters"
    requestId: str | None = None
    regenerate: bool = False
    locked: list[dict] = Field(default_factory=list)


@app.get("/api/catalog")
async def catalog():
    return {
        "personalities": rules.PERSONALITIES,
        "topics": list(rules.POOLS),
        "chaos": rules.CHAOS,
    }


@app.post("/api/spin")
async def spin():
    return {"count": rules.spin()}


@app.post("/api/health")
async def health(req: Request):
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(
                req.settings.get("url", "http://localhost:11434").rstrip("/")
                + "/api/tags"
            )
            response.raise_for_status()
        models = [m["name"] for m in response.json().get("models", [])]
        name = req.settings.get("model", "qwen3:4b")
        return {
            "ok": name in models,
            "models": models,
            "message": "Ready for a local party."
            if name in models
            else f"Model '{name}' is not downloaded. Run: ollama pull {name}, wait for completion, then retry. Or choose a downloaded model in Settings > AI.",
        }
    except Exception:
        return {
            "ok": False,
            "models": [],
            "message": "Cannot reach Ollama. Install Ollama, run ollama serve, then ollama pull qwen3:4b. Check your server URL and retry.",
        }


@app.post("/api/pool")
async def pool(req: Request):
    try:
        return await topic_pools.get(
            req.topic, req.category, req.settings, req.regenerate, req.locked
        )
    except Exception as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/generate/{kind}")
async def ideas(kind: str, req: Request):
    prompts = {
        "personality": 'Invent one funny, distinctive personality. Return {"name":"short label","description":"two sentences"}.',
        "topics": 'Suggest eight discussion topics for a character bingo party. Return {"topics":["topic"]}.',
    }
    if kind not in prompts:
        raise HTTPException(404, "Unknown generator")
    try:
        return await generate(
            req.settings, "Return valid JSON only.", prompts[kind], True
        )
    except Exception as exc:
        raise HTTPException(502, str(exc))


class TurnRequest(BaseModel):
    sessionId: str
    botId: str | None = None
    requestId: str | None = None


@app.post("/api/turn")
async def turn(req: TurnRequest):
    try:
        return await rounds.turn(req.sessionId, req.botId, req.requestId)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, "Local generation failed: " + str(exc))


@app.post("/api/rounds")
async def create_round(req: Request):
    try:
        if req.requestId:
            existing = storage.load("_setup_keys", req.requestId)
            if existing:
                return rounds.public(rounds.load(existing))
        result = rounds.create(req.state, req.settings)
        if req.requestId:
            storage.save("_setup_keys", req.requestId, result["sessionId"])
        return result
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/rounds/{sid}")
async def get_round(sid: str):
    s = rounds.load(sid)
    result = rounds.public(s)
    rounds.persist(s)
    return result


@app.post("/api/rounds/{sid}/fork")
async def fork_round(sid: str):
    return rounds.fork(sid)


class Control(BaseModel):
    action: str


@app.post("/api/rounds/{sid}/control")
async def control_round(sid: str, req: Control):
    try:
        return rounds.control(sid, req.action)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class Mark(BaseModel):
    index: int
    botId: str = ""


@app.post("/api/rounds/{sid}/mark")
async def mark_round(sid: str, req: Mark):
    try:
        return rounds.mark(sid, req.index)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/rounds/{sid}/accuse")
async def accuse_round(sid: str, req: Mark):
    try:
        return rounds.accuse(sid, req.index, req.botId)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class Question(BaseModel):
    text: str = Field(max_length=600)
    target: str = "all"


@app.post("/api/rounds/{sid}/question")
async def ask_round(sid: str, req: Question):
    try:
        return rounds.question(sid, req.text, req.target)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/rounds/{sid}/poll")
async def poll_round(sid: str):
    try:
        return await rounds.poll(sid)
    except HTTPException:
        raise
    except Exception as exc:
        rounds.control(sid, "pause")
        raise HTTPException(422, "Poll failed: " + str(exc))


class UpdateRound(BaseModel):
    settings: dict = Field(default_factory=dict)
    bots: list[dict] | None = None
    relationships: dict | None = None
    relationshipLocks: dict | None = None


@app.patch("/api/rounds/{sid}")
async def update_round(sid: str, req: UpdateRound):
    try:
        return rounds.settings(
            sid, req.settings, req.bots, req.relationships, req.relationshipLocks
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class RoundSave(BaseModel):
    sessionId: str
    name: str = Field(min_length=1, max_length=100)


@app.post("/api/round-saves")
async def save_round(req: RoundSave):
    rounds.save(req.sessionId, req.name)
    return {"ok": True}


@app.get("/api/round-saves")
async def round_saves():
    return storage.list("_round_saves")


@app.post("/api/round-saves/{name}/load")
async def load_round(name: str):
    try:
        return rounds.restore_save(name)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class KnowledgeImport(BaseModel):
    topic: str
    content: str = Field(max_length=2000000)
    format: str = "json"


@app.post("/api/knowledge/import")
async def import_knowledge(req: KnowledgeImport):
    try:
        return {"count": knowledge.import_profiles(req.topic, req.content, req.format)}
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/saves/{kind}")
async def list_saves(kind: str):
    if kind not in ("game", "board"):
        raise HTTPException(404, "Unknown public save type")
    return storage.list(kind)


@app.get("/api/saves/{kind}/{name}")
async def load(kind: str, name: str):
    if kind not in ("game", "board"):
        raise HTTPException(404, "Unknown public save type")
    value = storage.load(kind, name)
    if value is None:
        raise HTTPException(404, "Save not found")
    return value


@app.put("/api/saves/{kind}/{name}")
async def save(kind: str, name: str, value: dict):
    if kind not in ("game", "board"):
        raise HTTPException(404, "Unknown public save type")
    storage.save(kind, name, value)
    return {"ok": True}


@app.get("/api/voices")
async def voices():
    root = Path(os.getenv("PIPER_VOICE_DIR", "voices"))
    return {
        "piperAvailable": bool(piper_command()),
        "voices": [
            p.stem for p in root.glob("*.onnx") if p.with_suffix(".onnx.json").exists()
        ],
        "labels": VOICE_LABELS,
    }


class Speech(BaseModel):
    text: str = Field(max_length=6000)
    voice: str
    rate: float = Field(default=1, ge=0.5, le=2)


@app.post("/api/speech")
async def speech(req: Speech):
    root = Path(os.getenv("PIPER_VOICE_DIR", "voices")).resolve()
    model = root / (req.voice + ".onnx")
    command = piper_command()
    if (
        model.parent != root
        or not model.exists()
        or not model.with_suffix(".onnx.json").exists()
        or not command
    ):
        raise HTTPException(
            503, "Piper voice unavailable; select an installed browser voice."
        )
    key = hashlib.sha256((req.text + req.voice + str(req.rate)).encode()).hexdigest()
    cache = storage.path / "audio"
    cache.mkdir(exist_ok=True)
    path = cache / (key + ".wav")
    if not path.exists():

        def render():
            subprocess.run(
                [
                    *command,
                    "--model",
                    str(model),
                    "--output_file",
                    str(path),
                    "--length_scale",
                    str(1 / req.rate),
                ],
                input=req.text,
                text=True,
                check=True,
                timeout=60,
                capture_output=True,
            )

        try:
            await asyncio.to_thread(render)
        except Exception:
            path.unlink(missing_ok=True)
            raise HTTPException(
                503, "Piper failed. Browser speech fallback is available."
            )
        files = sorted(cache.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        for old in files[:-100]:
            old.unlink(missing_ok=True)
    return FileResponse(path, media_type="audio/wav")


frontend = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend.exists():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

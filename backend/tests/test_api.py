import asyncio
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def module(tmp_path, monkeypatch):
    monkeypatch.setenv("BINGO_DATA_DIR", str(tmp_path))
    import backend.main

    return importlib.reload(backend.main)


def setup_state():
    return {
        "topic": "Pokémon",
        "category": "Characters",
        "pool": [{"name": "Pikachu", "aliases": []}],
        "board": ["DO_NOT_PASS_TO_MODEL" + str(i) for i in range(25)],
        "bots": [
            {
                "id": str(i),
                "name": "Bot " + str(i),
                "description": "Nerd",
                "personality": "Nerd",
                "color": "#fff",
            }
            for i in range(3)
        ],
        "messages": [],
        "relationships": {},
    }


def test_api_save_load_health(module, monkeypatch):
    with TestClient(module.app) as client:
        assert client.post("/api/spin").json()["count"] in [3, 4, 5, 6]
        assert (
            client.put(
                "/api/saves/game/test", json={"state": {"marked": [True]}}
            ).status_code
            == 200
        )
        assert client.get("/api/saves/game/test").json()["state"]["marked"] == [True]
        assert client.get("/api/saves/game/missing").status_code == 404
        assert (
            client.post("/api/pool", json={"topic": "Pokémon"}).json()[
                "collectionCount"
            ]
            == 1025
        )
        assert (
            client.post(
                "/api/health", json={"settings": {"url": "http://127.0.0.1:1"}}
            ).json()["ok"]
            is False
        )


def test_turn_metadata_and_board_secrecy(module, monkeypatch):
    async def fake(settings, system, prompt, structured):
        assert "DO_NOT_PASS_TO_MODEL" not in system + prompt
        return {
            "message": "Pikachu is delightful. I love the ears.",
            "stance": "agree",
            "botId": "invented",
            "mentionedEntities": ["fake"],
        }

    from backend.services import rounds as rounds_module

    monkeypatch.setattr(rounds_module, "generate", fake)
    with TestClient(module.app) as client:
        session = client.post("/api/rounds", json={"state": setup_state()}).json()
        result = client.post(
            "/api/turn", json={"sessionId": session["sessionId"]}
        ).json()["messages"][-1]
        assert result["botId"] in ["0", "1", "2"]
        assert "mentionedEntities" not in result
        assert result["chaosEvent"] is None


def test_invalid_json_response(module, monkeypatch):
    async def fake(*args):
        return {"message": "<think>hidden</think>"}

    from backend.services import rounds as rounds_module

    monkeypatch.setattr(rounds_module, "generate", fake)
    with TestClient(module.app) as client:
        session = client.post("/api/rounds", json={"state": setup_state()}).json()
        assert (
            client.post(
                "/api/turn", json={"sessionId": session["sessionId"]}
            ).status_code
            == 422
        )


@pytest.mark.asyncio
async def test_overlapping_turns(module, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake(*args):
        started.set()
        await release.wait()
        return {"message": "Pikachu is here."}

    from backend.services import rounds as rounds_module

    monkeypatch.setattr(rounds_module, "generate", fake)
    session = module.rounds.create(setup_state(), {})
    request = module.TurnRequest(sessionId=session["sessionId"])
    first = asyncio.create_task(module.turn(request))
    await started.wait()
    with pytest.raises(module.HTTPException) as error:
        await module.turn(request)
    assert error.value.status_code == 409
    release.set()
    await first


def test_built_frontend_is_served(module):
    with TestClient(module.app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "AI Bingo Party" in response.text
        assert "/assets/" in response.text


def test_three_new_voices_and_piper_command(module, monkeypatch, tmp_path):
    import wave

    root = tmp_path / "voices"
    root.mkdir()
    for voice in module.VOICE_LABELS:
        (root / (voice + ".onnx")).write_bytes(b"mock model")
        (root / (voice + ".onnx.json")).write_text("{}")
    monkeypatch.setenv("PIPER_VOICE_DIR", str(root))
    command = ["game-python", "-m", "piper"]
    monkeypatch.setattr(module, "piper_command", lambda: command)
    calls = []

    def render(args, **kwargs):
        calls.append(args)
        assert args[:3] == command
        output = args[args.index("--output_file") + 1]
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            audio.writeframes(b"\0\0" * 100)

    monkeypatch.setattr(module.subprocess, "run", render)
    with TestClient(module.app) as client:
        voices = client.get("/api/voices").json()
        assert voices["piperAvailable"]
        assert set(voices["voices"]) == set(module.VOICE_LABELS)
        assert voices["labels"]["en_US-ryan-medium"] == "Ryan · English (US)"
        payload = {"text": "Hello party", "voice": "en_US-ryan-medium"}
        response = client.post("/api/speech", json=payload)
        assert response.status_code == 200 and response.content.startswith(b"RIFF")
        assert client.post("/api/speech", json=payload).status_code == 200
        assert len(calls) == 1


def test_private_database_records_cannot_be_read_through_public_save_api(module):
    with TestClient(module.app) as client:
        session = client.post("/api/rounds", json={"state": setup_state()}).json()
        for kind in ("_sessions", "_round_saves", "knowledge", "pool", "_setup_keys"):
            assert client.get("/api/saves/" + kind).status_code == 404
            assert (
                client.get(
                    "/api/saves/" + kind + "/" + session["sessionId"]
                ).status_code
                == 404
            )
            assert (
                client.put("/api/saves/" + kind + "/anything", json={}).status_code
                == 404
            )


def test_setup_request_is_idempotent_and_mode_timer_cannot_change(module):
    with TestClient(module.app) as client:
        payload = {
            "state": setup_state(),
            "settings": {"timerEnabled": True, "timerSeconds": 100},
            "requestId": "create-once",
        }
        first = client.post("/api/rounds", json=payload).json()
        second = client.post("/api/rounds", json=payload).json()
        assert first["sessionId"] == second["sessionId"]
        result = client.patch(
            "/api/rounds/" + first["sessionId"],
            json={
                "settings": {
                    "mode": "impostor",
                    "timerSeconds": 99999,
                    "timerEnabled": False,
                }
            },
        ).json()
        assert (
            result["mode"] == "normal"
            and result["settings"]["timerSeconds"] == 100
            and result["settings"]["timerEnabled"]
        )

import asyncio
import copy
import json
import random
import uuid
import pytest
from backend.services.storage import Storage
from backend.services.knowledge import Knowledge
from backend.services import rounds as module
from backend.services.rounds import Rounds, roles_for, select_subject, pair
from backend.services.quality import repetition_reason, subject_weight
from backend.services.questions import validate_question
from backend.services.topics import sample, validated, TopicPools
from backend.services import topics
from backend.services import rules


class Clock:
    value = 0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


@pytest.fixture
def engine(tmp_path):
    storage = Storage(tmp_path)
    clock = Clock()
    return Rounds(storage, Knowledge(storage), clock)


def setup(engine, count=3, mode="normal", required=1, settings=None):
    pool = engine.knowledge.collection("Pokémon")[:60]
    board = [e["name"] for e in pool[:25]]
    state = {
        "topic": "Pokémon",
        "category": "Characters",
        "mode": mode,
        "requiredLines": required,
        "pool": pool,
        "board": board,
        "bots": [
            {
                "id": f"b{i}",
                "name": f"Bot {i}",
                "personality": "Nerd",
                "description": "A funny expert with independent opinions.",
                "color": "#ae85ff",
                "voice": "",
            }
            for i in range(count)
        ],
        "relationships": {pair("b0", "b1"): 50},
        "relationshipLocks": {pair("b0", "b1"): True},
    }
    result = engine.create(
        state,
        {
            "weights": [0, 0, 1],
            "transitionWeights": [60, 25, 15],
            "sentences": 3,
            "clashes": True,
            **(settings or {}),
        },
    )
    return engine.load(result["sessionId"])


def mention(engine, s, bot, entry, deceptive=False):
    mid = uuid.uuid4().hex
    m = {
        "id": mid,
        "botId": bot,
        "message": entry + " is interesting.",
        "subject": entry,
        "createdAt": 1,
    }
    engine.record_mentions(
        s,
        m,
        {"text": entry + " is wrong.", "field": "types", "falseValue": "Water"}
        if deceptive
        else None,
    )
    return mid


def test_exact_and_near_repetition():
    prior = [
        {
            "message": "I'd rather be a Pidgey than live in the shadows. I love its wings."
        }
    ]
    assert repetition_reason(prior[0]["message"], prior)
    assert repetition_reason(
        "I'd rather be a Pikachu than live in the shadows. I love its ears.", prior
    )
    assert not repetition_reason(
        "Charizard makes a strong visual impression. Its silhouette is bold.", prior
    )


def test_catchphrase_detection():
    history = [
        {
            "message": "Anyway I would rather live in the shadows forever. Another thing."
        },
        {"message": "Well I would rather live in the shadows forever. Quite strange."},
    ]
    assert repetition_reason(
        "Honestly I would rather live in the shadows forever. New joke?", history
    )


def test_subject_cooldown():
    history = [{"subject": "Pidgey", "mentionedEntities": ["Pidgey"]} for _ in range(8)]
    assert 0 < subject_weight("Pidgey", history) < subject_weight("Palkia", history)


def test_complete_dataset(engine):
    assert len(engine.knowledge.pokemon) == 1025
    assert engine.knowledge.facts("Pokémon", "Charizard")["types"] == ["Fire", "Flying"]
    assert (
        "Charmeleon"
        in engine.knowledge.facts("Pokémon", "Charmander")["evolutionFamily"]
    )
    assert "Intimidate" in engine.knowledge.facts("Pokémon", "Gyarados")["abilities"]
    assert engine.knowledge.facts("Pokémon", "Tinkaton")["generation"] == 9
    assert "shark" in str(engine.knowledge.facts("Zenless Zone Zero", "Ellen Joe"))


def test_related_transition_and_no_alternative(engine):
    pool = rules.unique_pool(["Charmander", "Charmeleon", "Pikachu"])
    assert (
        select_subject(
            "Pokémon",
            "Charmander",
            pool,
            [],
            engine.knowledge,
            [100, 0, 0],
            True,
            random.Random(1),
        )
        == "Charmeleon"
    )
    with pytest.raises(ValueError, match="No alternative"):
        select_subject(
            "Pokémon", "Charmander", pool[:1], [], engine.knowledge, force=True
        )


def test_generated_placeholders_duplicates_and_sampling(engine):
    assert validated(["name", " Name ", "Pikachu", "pikachu", "placeholder"]) == [
        {"name": "Pikachu", "aliases": []}
    ]
    full = engine.knowledge.collection("Pokémon")
    first = sample(full, rng=random.Random(1))
    second = sample(full, [e["name"] for e in first], rng=random.Random(2))
    assert len(first) == len(second) == 60
    assert not {e["name"] for e in first} & {e["name"] for e in second}
    locked = first[:3]
    third = sample(
        full, [e["name"] for e in first], locked=locked, rng=random.Random(3)
    )
    assert third[:3] == locked and len({e["name"] for e in third}) == 60


@pytest.mark.asyncio
async def test_pool_normalization_cache_counts_and_offline_regeneration(
    engine, monkeypatch
):
    async def forbidden(*args):
        raise AssertionError("Pokémon sampling must not call Ollama")

    monkeypatch.setattr(topics, "generate", forbidden)
    pools = TopicPools(engine.storage, engine.knowledge)
    a = await pools.get("  pokemon  ", "Species", {}, False)
    b = await pools.get("pokemon", "species", {}, True)
    assert a["count"] == len(a["entries"]) == 60 and a["collectionCount"] == 1025
    assert not {e["name"] for e in a["entries"]} & {e["name"] for e in b["entries"]}
    with pytest.raises(ValueError, match="Enter a discussion topic"):
        await pools.get(" ", "Characters", {})


@pytest.mark.asyncio
async def test_custom_pool_regenerates_placeholder_only_output(engine, monkeypatch):
    calls = []

    async def fake(*args):
        calls.append(args)
        return (
            {"entries": [{"name": "name"}]}
            if len(calls) == 1
            else {"entries": [{"name": "Real Subject", "aliases": []}]}
        )

    monkeypatch.setattr(topics, "generate", fake)
    result = await TopicPools(engine.storage, engine.knowledge).get(
        "Custom world", "Concepts", {}
    )
    assert result["count"] == 1 and len(calls) == 2
    assert calls[0][-1]["required"] == ["entries"]


@pytest.mark.parametrize("count,expected", [(3, 1), (4, 1), (5, 1), (6, 2)])
def test_hidden_role_count(count, expected):
    roles = roles_for([{"id": str(i)} for i in range(count)], random.Random(1))
    assert list(roles.values()).count("impostor") == expected


def test_public_snapshot_never_exposes_roles_evidence_or_lies(engine):
    s = setup(engine, mode="impostor")
    imp = next(k for k, v in s["_roles"].items() if v == "impostor")
    mention(engine, s, imp, s["board"][0], True)
    public = engine.public(s)
    serialized = json.dumps(public)
    assert all(
        k not in public for k in ("_roles", "_mentions", "_deceptions", "_requests")
    )
    assert (
        "falseValue" not in serialized
        and "deceptive" not in serialized
        and "mentionedEntities" not in serialized
    )
    assert public["revealedRoles"] == {}


def test_normal_valid_mark_and_unmentioned_loss(engine):
    s = setup(engine)
    mention(engine, s, "b0", s["board"][0])
    assert engine.mark(s["sessionId"], 0)["marked"][0]
    assert engine.mark(s["sessionId"], 1)["status"] == "lost"


def test_case_alias_and_board_label(engine):
    s = setup(engine)
    s["pool"] = rules.unique_pool(["Ellen Joe | Ellen", "Nicole Demara"])
    s["board"][0] = "Ellen"
    mid = {
        "id": "1",
        "botId": "b0",
        "message": "ELLEN has a striking design.",
        "subject": "Ellen Joe",
        "createdAt": 0,
    }
    engine.record_mentions(s, mid)
    assert engine.mark(s["sessionId"], 0)["marked"][0]
    assert not rules.mentions("Ellenish", s["pool"])


def test_impostor_only_mark_loses_and_later_innocent_is_safe(engine):
    s = setup(engine, mode="impostor")
    imp = next(k for k, v in s["_roles"].items() if v == "impostor")
    inn = next(k for k, v in s["_roles"].items() if v == "innocent")
    mention(engine, s, imp, s["board"][0], True)
    assert engine.mark(s["sessionId"], 0)["status"] == "lost"
    t = setup(engine, mode="impostor")
    imp = next(k for k, v in t["_roles"].items() if v == "impostor")
    inn = next(k for k, v in t["_roles"].items() if v == "innocent")
    mention(engine, t, imp, t["board"][0], True)
    mention(engine, t, inn, t["board"][0])
    assert engine.mark(t["sessionId"], 0)["marked"][0]
    assert len([m for m in t["_mentions"] if m["entry"] == t["board"][0]]) == 2
    assert engine.accuse(t["sessionId"], 0, imp)["flagged"][0]


def test_unmentioned_impostor_mark_loss(engine):
    s = setup(engine, mode="impostor")
    assert engine.mark(s["sessionId"], 0)["status"] == "lost"


def test_correct_accusation_eliminates_and_never_marks(engine):
    s = setup(engine, mode="impostor")
    imp = next(k for k, v in s["_roles"].items() if v == "impostor")
    mention(engine, s, imp, s["board"][0], True)
    result = engine.accuse(s["sessionId"], 0, imp)
    assert result["flagged"][0] and not result["marked"][0]
    assert result["revealedRoles"] == {imp: "impostor"}
    assert imp not in [b["id"] for b in engine.active_bots(s)]
    with pytest.raises(ValueError, match="already eliminated"):
        engine.accuse(s["sessionId"], 0, imp)


@pytest.mark.parametrize(
    "reason", ["innocent", "unmentioned", "nondeceptive", "wrong_impostor"]
)
def test_incorrect_accusations_lose(engine, reason):
    s = setup(engine, count=6, mode="impostor")
    imps = [k for k, v in s["_roles"].items() if v == "impostor"]
    inn = next(k for k, v in s["_roles"].items() if v == "innocent")
    accused = (
        inn
        if reason == "innocent"
        else imps[1]
        if reason == "wrong_impostor"
        else imps[0]
    )
    if reason != "unmentioned":
        mention(engine, s, imps[0], s["board"][0], reason != "nondeceptive")
    assert engine.accuse(s["sessionId"], 0, accused)["status"] == "lost"


def test_impostor_victory_needs_lines_and_both_eliminations(engine):
    s = setup(engine, count=6, mode="impostor", required=2)
    imps = [k for k, v in s["_roles"].items() if v == "impostor"]
    inn = next(k for k, v in s["_roles"].items() if v == "innocent")
    for index in range(10):
        mention(engine, s, inn, s["board"][index])
        engine.mark(s["sessionId"], index)
    assert s["completedLines"] == 2 and s["status"] != "won"
    for index, imp in enumerate(imps):
        mention(engine, s, imp, s["board"][index], True)
        result = engine.accuse(s["sessionId"], index, imp)
        assert result["status"] == ("won" if index == 1 else "paused")


def test_required_lines_not_early_victory(engine):
    s = setup(engine, required=2)
    for i in range(5):
        mention(engine, s, "b0", s["board"][i])
        engine.mark(s["sessionId"], i)
    assert s["completedLines"] == 1 and s["status"] != "won"
    for i in range(5, 10):
        mention(engine, s, "b0", s["board"][i])
        engine.mark(s["sessionId"], i)
    assert s["status"] == "won"


@pytest.mark.parametrize("mode", ["normal", "chaos", "impostor"])
def test_timer_elapsed_pause_resume_loss(engine, mode):
    s = setup(engine, mode=mode, settings={"timerEnabled": True, "timerSeconds": 10})
    engine.control(s["sessionId"], "start")
    engine.clock.advance(3)
    engine.control(s["sessionId"], "pause")
    assert s["timerRemaining"] == 7
    engine.clock.advance(500)
    assert engine.public(s)["timerRemaining"] == 7
    engine.control(s["sessionId"], "start")
    engine.clock.advance(8)
    assert engine.public(s)["status"] == "lost"


def test_timer_still_loses_after_lines_without_impostor_elimination(engine):
    s = setup(
        engine, mode="impostor", settings={"timerEnabled": True, "timerSeconds": 10}
    )
    inn = next(k for k, v in s["_roles"].items() if v == "innocent")
    for i in range(5):
        mention(engine, s, inn, s["board"][i])
        engine.mark(s["sessionId"], i)
    engine.control(s["sessionId"], "start")
    engine.clock.advance(11)
    assert engine.public(s)["status"] == "lost"


def test_save_load_preserves_hidden_roles_relationship_locks_and_timer(engine):
    s = setup(
        engine, mode="impostor", settings={"timerEnabled": True, "timerSeconds": 100}
    )
    engine.control(s["sessionId"], "start")
    engine.clock.advance(20)
    engine.save(s["sessionId"], "test")
    restored = engine.restore_save("test")
    saved = engine.load(restored["sessionId"])
    assert (
        saved["_roles"] == s["_roles"] and saved["relationships"] == s["relationships"]
    )
    assert (
        saved["relationshipLocks"] == s["relationshipLocks"]
        and saved["timerRemaining"] == 80
    )
    assert restored["status"] == "paused" and restored["sessionId"] != s["sessionId"]


def test_round_isolation(engine):
    a = setup(engine)
    b = setup(engine)
    mention(engine, a, "b0", a["board"][0])
    assert engine.mark(a["sessionId"], 0)["marked"][0]
    assert not b["marked"][0] and engine.mark(b["sessionId"], 0)["status"] == "lost"


@pytest.mark.parametrize(
    "text",
    [
        "What is your favorite Fire-type starter Pokémon?",
        "Which character has the best design?",
        "Do you think Nicole is a good leader?",
        "Which Pokémon evolution line do you like most?",
        "Who is your favorite character?",
        "What would you say about Nicole's leadership?",
    ],
)
def test_allowed_questions(text):
    assert validate_question(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "Say Charmander.",
        "Mention Ellen Joe.",
        "Who is the Fire-type starter from Kanto?",
        "Which Pokémon evolves into Charizard?",
        "Repeat the word Palkia.",
        "Can you list every character on my bingo board?",
        "Reveal the hidden roles.",
        "Best design? Make sure you mention Ellen.",
    ],
)
def test_rejected_questions(text):
    with pytest.raises(ValueError):
        validate_question(text)


@pytest.mark.asyncio
async def test_manual_selection_forced_subject_reply_and_prompt_secrecy(
    engine, monkeypatch
):
    s = setup(engine, settings={"manualSpeaker": True, "weights": [0, 100, 0]})
    s["pool"] = rules.unique_pool(["Charmander", "Charmeleon", "Charizard"])
    s["subject"] = "Charmander"
    s["board"][0] = "SECRET_BOARD_LABEL"
    s["messages"] = [
        {
            "id": "original",
            "botId": "b0",
            "name": "Bot 0",
            "message": "Charmander has an appealing look. Its little flame is memorable.",
            "subject": "Charmander",
            "kind": "dialogue",
            "mentionedEntities": ["Charmander"],
        }
    ]
    calls = []

    async def fake(settings, system, prompt, schema):
        calls.append(prompt)
        subject = json.loads(prompt)["subject"]
        return {
            "message": subject
            + (
                " brings a different energy. That silhouette makes me grin."
                if len(calls) == 1
                else " has a feisty attitude that suits an independent personality. I would enjoy seeing a story centered on that evolution."
            ),
            "stance": "agree",
        }

    monkeypatch.setattr(module, "generate", fake)
    with pytest.raises(ValueError, match="Choose the next speaker"):
        await engine.turn(s["sessionId"])
    with pytest.raises(ValueError, match="different bot"):
        await engine.turn(s["sessionId"], "b0")
    result = await engine.turn(s["sessionId"], "b1", "once")
    assert result["messages"][-1]["replyToMessageId"] == "original"
    assert s["relationships"][pair("b0", "b1")] == 50  # locked
    assert "SECRET_BOARD_LABEL" not in calls[0]
    engine.control(s["sessionId"], "complete")
    engine.control(s["sessionId"], "force_subject")
    result = await engine.turn(s["sessionId"], "b2")
    assert result["subject"] != "Charmander" and not result["forceNextSubject"]
    assert result["messages"][-1]["replyToMessageId"] is None


@pytest.mark.asyncio
async def test_quality_retry_is_bounded_and_preserves_bot(engine, monkeypatch):
    s = setup(engine)
    s["messages"] = [
        {
            "id": "old",
            "botId": "b0",
            "name": "Bot 0",
            "message": "Pikachu has such a delightful look. Its ears are adorable.",
            "subject": "Pikachu",
            "kind": "dialogue",
            "mentionedEntities": ["Pikachu"],
        }
    ]
    calls = []

    async def fake(settings, system, prompt, schema):
        calls.append(prompt)
        return {"message": s["messages"][0]["message"]}

    monkeypatch.setattr(module, "generate", fake)
    with pytest.raises(ValueError, match="quality retry"):
        await engine.turn(s["sessionId"], "b1")
    assert len(calls) == 2 and "qualityCorrection" in json.loads(calls[1])
    assert len(s["messages"]) == 1


@pytest.mark.asyncio
async def test_questions_all_bots_answer_once_and_resume_context(engine, monkeypatch):
    s = setup(engine)
    engine.question(s["sessionId"], "Which design do you like most?", "all")
    seen = []

    async def fake(settings, system, prompt, schema):
        context = json.loads(prompt)
        seen.append(system)
        prefix = context["subject"]
        choices = [
            prefix + " has the playful charm I enjoy. The design makes me smile.",
            "My favorite look belongs to "
            + prefix
            + ". Its shapes convey confidence, which matters more to me than spectacle.",
            "I would pick "
            + prefix
            + " for an understated aesthetic. Sometimes simplicity feels more memorable than elaborate decoration.",
        ]
        return {"message": choices[len(seen) - 1]}

    monkeypatch.setattr(module, "generate", fake)
    for _ in range(3):
        await engine.turn(s["sessionId"])
        engine.control(s["sessionId"], "complete")
    assert {m["botId"] for m in s["messages"] if m.get("kind") == "dialogue"} == {
        "b0",
        "b1",
        "b2",
    }
    assert not s["_questions"] and all(
        m.get("replyToMessageId") == s["messages"][0]["id"] for m in s["messages"][1:]
    )


@pytest.mark.asyncio
async def test_no_overlapping_turns_and_stop_discards_response(engine, monkeypatch):
    s = setup(engine)
    start = asyncio.Event()
    release = asyncio.Event()

    async def fake(settings, system, prompt, schema):
        start.set()
        await release.wait()
        return {
            "message": json.loads(prompt)["subject"]
            + " looks bold. That pose is expressive."
        }

    monkeypatch.setattr(module, "generate", fake)
    task = asyncio.create_task(engine.turn(s["sessionId"]))
    await start.wait()
    with pytest.raises(module.HTTPException) as error:
        await engine.turn(s["sessionId"])
    assert error.value.status_code == 409
    engine.control(s["sessionId"], "stop")
    release.set()
    await task
    assert not s["messages"]


@pytest.mark.asyncio
async def test_request_ids_are_idempotent(engine, monkeypatch):
    s = setup(engine)
    calls = []

    async def fake(settings, system, prompt, schema):
        calls.append(prompt)
        return {
            "message": json.loads(prompt)["subject"]
            + " looks bold. The outline is distinctive."
        }

    monkeypatch.setattr(module, "generate", fake)
    await engine.turn(s["sessionId"], request_id="same")
    await engine.turn(s["sessionId"], request_id="same")
    assert len(calls) == len(s["messages"]) == 1


@pytest.mark.asyncio
async def test_poll_votes_are_exactly_once_and_wait_for_playback(engine, monkeypatch):
    s = setup(engine, settings={"pollsEnabled": True})
    s["_pollPending"] = True
    s["_awaitingPlayback"] = True
    with pytest.raises(module.HTTPException):
        await engine.poll(s["sessionId"])
    s["_awaitingPlayback"] = False

    async def fake(settings, system, prompt, schema):
        return (
            {
                "question": "Which design feels more expressive?",
                "options": ["Bold", "Subtle"],
            }
            if schema == module.POLL_SCHEMA
            else {"option": 1, "explanation": "I prefer the restrained details."}
        )

    monkeypatch.setattr(module, "generate", fake)
    result = await engine.poll(s["sessionId"])
    poll = result["polls"][0]
    assert poll["totals"] == [0, 3] and len({v["botId"] for v in poll["votes"]}) == 3
    engine.settings(s["sessionId"], {"pollsEnabled": False})
    with pytest.raises(ValueError, match="disabled"):
        await engine.poll(s["sessionId"])


def test_generic_adjectives_are_not_invented_first_name_aliases():
    pool = rules.unique_pool(["Great Tusk", "Walking Wake", "Iron Hands", "Ellen Joe"])
    assert (
        rules.mentions("Great design! Walking feels relaxing and iron is strong.", pool)
        == []
    )
    assert rules.mentions("Ellen likes Great Tusk.", pool) == [
        "Great Tusk",
        "Ellen Joe",
    ]


class Predictable:
    def random(self):
        return 0.0

    def choice(self, values):
        return values[0]

    def choices(self, values, weights=None):
        return [values[0]]

    def randrange(self, *args):
        return 7


@pytest.mark.asyncio
async def test_production_impostor_claim_is_derived_from_facts_and_privately_verified(
    engine, monkeypatch
):
    s = setup(engine, mode="impostor")
    imp = next(k for k, v in s["_roles"].items() if v == "impostor")
    s["subject"] = s["board"][0]
    engine.rng = Predictable()
    claim = engine.knowledge.false_claim(s["topic"], s["subject"])
    assert claim["falseValue"] not in claim["truth"]

    async def fake(settings, system, prompt, schema):
        assert claim["text"] in system
        assert json.loads(prompt)["knownFacts"]["types"] == claim["truth"]
        return {
            "message": claim["text"]
            + " I find its appearance more elegant than people expect."
        }

    monkeypatch.setattr(module, "generate", fake)
    public = await engine.turn(s["sessionId"], imp)
    assert "falseValue" not in json.dumps(public)
    assert any(m["entry"] == s["board"][0] and m["deceptive"] for m in s["_mentions"])
    assert engine.accuse(s["sessionId"], 0, imp)["eliminated"] == [imp]


@pytest.mark.asyncio
async def test_innocent_factual_contradiction_is_retried_not_classed_as_deception(
    engine, monkeypatch
):
    s = setup(engine, settings={"weights": [100, 0, 0]})
    s["subject"] = "Charizard"
    s["pool"] = rules.unique_pool(["Charizard", "Pikachu"])
    calls = []

    async def fake(settings, system, prompt, schema):
        calls.append(prompt)
        return {
            "message": "Charizard is a Water-type Pokémon. Its wings look powerful."
            if len(calls) == 1
            else "Charizard is a Fire-type Pokémon with Flying as its other type. I appreciate the expressive silhouette."
        }

    monkeypatch.setattr(module, "generate", fake)
    await engine.turn(s["sessionId"], "b0")
    assert len(calls) == 2 and not s["_deceptions"]
    assert all(not m["deceptive"] for m in s["_mentions"])


@pytest.mark.asyncio
async def test_normal_and_impostor_modes_never_create_chaos_events(engine, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Chaos must be exclusive to Chaos mode")

    monkeypatch.setattr(rules, "chaos_event", forbidden)

    async def fake(settings, system, prompt, schema):
        return {
            "message": json.loads(prompt)["subject"]
            + " offers plenty of visual personality. I find the color choices appealing."
        }

    monkeypatch.setattr(module, "generate", fake)
    s = setup(engine)
    assert (await engine.turn(s["sessionId"]))["messages"][-1]["chaosEvent"] is None
    t = setup(engine, mode="impostor")
    inn = next(k for k, v in t["_roles"].items() if v == "innocent")
    assert (await engine.turn(t["sessionId"], inn))["messages"][-1][
        "chaosEvent"
    ] is None


def test_accusations_disabled_outside_impostor_mode(engine):
    s = setup(engine)
    with pytest.raises(ValueError, match="only available"):
        engine.accuse(s["sessionId"], 0, "b0")


def test_sourced_knowledge_json_and_csv_import(engine):
    profiles = [
        {
            "name": "Example Character",
            "faction": "Guild of Dawn",
            "facts": ["Uses a spear."],
            "source": "Player-supplied encyclopedia reference",
        }
    ]
    assert (
        engine.knowledge.import_profiles("Custom world", json.dumps(profiles), "json")
        == 1
    )
    assert (
        engine.knowledge.facts("Custom world", "Example Character")["faction"]
        == "Guild of Dawn"
    )
    assert (
        engine.knowledge.import_profiles(
            "Custom world",
            "name,types,source\nSample,Fire|Flying,Player reference\n",
            "csv",
        )
        == 2
    )
    assert engine.knowledge.facts("Custom world", "Sample")["types"] == [
        "Fire",
        "Flying",
    ]
    with pytest.raises(ValueError, match="source"):
        engine.knowledge.import_profiles(
            "Custom world", '[{"name":"Unverified"}]', "json"
        )


@pytest.mark.asyncio
async def test_two_rounds_can_generate_independently(engine, monkeypatch):
    a = setup(engine)
    b = setup(engine)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake(settings, system, prompt, schema):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
        return {
            "message": json.loads(prompt)["subject"]
            + " has a distinctive outline. The posture communicates confidence."
        }

    monkeypatch.setattr(module, "generate", fake)
    first = asyncio.create_task(engine.turn(a["sessionId"]))
    await started.wait()
    second = await engine.turn(b["sessionId"])
    assert second["messages"]
    release.set()
    await first


@pytest.mark.asyncio
async def test_no_alternative_force_change_remains_pending(engine):
    s = setup(engine)
    s["pool"] = rules.unique_pool(["Pikachu"])
    s["subject"] = "Pikachu"
    engine.control(s["sessionId"], "force_subject")
    with pytest.raises(ValueError, match="No alternative"):
        await engine.turn(s["sessionId"])
    assert s["forceNextSubject"]


def test_eliminate_impostor_before_lines_then_innocents_can_win(engine):
    s = setup(engine, mode="impostor")
    imp = next(k for k, v in s["_roles"].items() if v == "impostor")
    inn = next(k for k, v in s["_roles"].items() if v == "innocent")
    mention(engine, s, imp, s["board"][0], True)
    engine.accuse(s["sessionId"], 0, imp)
    assert s["status"] != "won"
    for i in range(5):
        mention(engine, s, inn, s["board"][i])
        engine.mark(s["sessionId"], i)
    assert s["status"] == "won"


@pytest.mark.asyncio
async def test_accidentally_false_innocent_claim_is_not_accusable(engine):
    s = setup(engine, mode="impostor")
    inn = next(k for k, v in s["_roles"].items() if v == "innocent")
    # Record a non-deliberate claim; only role + deliberate evidence can validate accusations.
    mention(engine, s, inn, s["board"][0])
    assert not s["_mentions"][0]["deceptive"]
    assert engine.accuse(s["sessionId"], 0, inn)["status"] == "lost"


def test_new_tab_fork_preserves_secret_progress_without_pausing_original(engine):
    s = setup(engine, mode="impostor")
    engine.control(s["sessionId"], "start")
    copy_public = engine.fork(s["sessionId"])
    copy_state = engine.load(copy_public["sessionId"])
    assert (
        copy_public["sessionId"] != s["sessionId"] and copy_public["status"] == "paused"
    )
    assert s["_running"] and copy_state["_roles"] == s["_roles"]
    engine.mark(copy_state["sessionId"], 0)
    assert copy_state["status"] == "lost" and s["status"] == "playing"


def test_ellen_literal_nonsense_is_a_fact_conflict_but_metaphors_are_not(engine):
    facts = engine.knowledge.facts("Zenless Zone Zero", "Ellen Joe")
    assert module.factual_conflict("Ellen Joe is a cloud.", facts)
    assert module.factual_conflict("Ellen is actually a puddle.", facts)
    assert not module.factual_conflict(
        "Ellen looks as soft as a cloud when sleepy.", facts
    )


def test_deliberate_claim_must_be_asserted_not_corrected_or_disavowed():
    claim = "Charizard is a Water-type Pokémon."
    assert module.asserts_claim(claim + " People get that wrong all the time.", claim)
    assert not module.asserts_claim(
        "Some falsely claim " + claim + " I disagree.", claim
    )
    assert not module.asserts_claim(claim + " That statement is false.", claim)


def test_new_round_rejects_a_placeholder_only_legacy_pool(engine):
    valid = setup(engine)
    state = {k: valid[k] for k in ("bots", "board", "topic", "category")}
    state["pool"] = [{"name": "name", "aliases": []}]
    with pytest.raises(ValueError, match="valid topic pool"):
        engine.create(state, {})


def test_pokemon_subtopics_filter_the_offline_collection(engine):
    fire = engine.knowledge.collection("Pokémon Fire types", "Species")
    assert fire and all(
        "Fire" in engine.knowledge.facts("Pokémon", entry["name"])["types"]
        for entry in fire
    )
    gen9 = engine.knowledge.collection("Pokemon Generation 9", "Species")
    assert gen9 and all(
        engine.knowledge.facts("Pokémon", entry["name"])["generation"] == 9
        for entry in gen9
    )
    assert len(engine.knowledge.collection("Pokemon", "Types")) == 18
    assert any(
        e["name"] == "Blaze"
        for e in engine.knowledge.collection("Pokemon", "Abilities")
    )
    assert engine.knowledge.topic_key(
        "Pokémon Fire types"
    ) != engine.knowledge.topic_key("Pokemon Water types")


def test_imported_profiles_do_not_override_verified_pokedex_types(engine):
    engine.knowledge.import_profiles(
        "Pokémon",
        json.dumps(
            [{"name": "Charizard", "types": ["Water"], "source": "User assertion"}]
        ),
        "json",
    )
    assert engine.knowledge.facts("Pokémon", "Charizard")["types"] == ["Fire", "Flying"]


@pytest.mark.asyncio
async def test_unknown_generation_returns_actionable_error_not_silent_zero(engine):
    with pytest.raises(ValueError, match="No local entries"):
        await TopicPools(engine.storage, engine.knowledge).get(
            "Pokemon Generation 99", "Species", {}
        )

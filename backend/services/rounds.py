"""Authoritative isolated rounds. Hidden roles/evidence never enter public snapshots."""

import asyncio
from collections import Counter
from difflib import SequenceMatcher
import copy
import json
import math
import random
import re
import secrets
import time
import uuid
from fastapi import HTTPException
from . import rules
from .ollama import generate, TURN_SCHEMA
from .quality import repetition_reason, subject_weight, normalized
from .questions import validate_question
from .topics import validated as validated_pool

MODES = {"normal", "chaos", "impostor"}
TERMINAL = {"won", "lost"}
PUBLIC_MESSAGE = (
    "id",
    "botId",
    "name",
    "personality",
    "color",
    "subject",
    "conversationAction",
    "message",
    "chaosEvent",
    "replyToMessageId",
    "kind",
    "questionId",
    "createdAt",
)
POLL_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 4,
        },
    },
    "required": ["question", "options"],
}
VOTE_SCHEMA = {
    "type": "object",
    "properties": {"option": {"type": "integer"}, "explanation": {"type": "string"}},
    "required": ["option", "explanation"],
}


def pair(a, b):
    return "|".join(sorted([a, b]))


def roles_for(bots, rng=random):
    chosen = {b["id"] for b in rng.sample(bots, 2 if len(bots) == 6 else 1)}
    return {b["id"]: "impostor" if b["id"] in chosen else "innocent" for b in bots}


def select_subject(
    topic, current, pool, history, knowledge, weights=None, force=False, rng=random
):
    names = [p["name"] for p in pool if p["name"] != current]
    if not names:
        if force:
            raise ValueError(
                "No alternative subject exists in this pool. Add more real entries to change subjects."
            )
        return current or pool[0]["name"]
    strong, weak = knowledge.related(topic, current, names)
    weights = weights or [60, 25, 15]
    if (
        len(weights) != 3
        or any(not isinstance(w, (int, float)) or w < 0 for w in weights)
        or sum(weights) <= 0
    ):
        raise ValueError(
            "Transition weights must be three nonnegative values with a positive total."
        )
    group = (
        rng.choices([strong, weak, names], weights=weights)[0]
        or weak
        or strong
        or names
    )
    return rng.choices(group, weights=[subject_weight(n, history) for n in group])[0]


def factual_conflict(text, facts):
    names = [
        facts.get("name", ""),
        *rules.VERIFIED_ALIASES.get(facts.get("name", ""), []),
    ]
    if facts.get("name") == "Ellen Joe" and re.search(
        r"(?<!\w)(?:"
        + "|".join(re.escape(n) for n in names)
        + r")\s+is(?: actually)?\s+(?:an?\s+)?(?:cloud|puddle)\b",
        text,
        re.I,
    ):
        return True
    if not facts.get("types"):
        return False
    name = re.escape(facts["name"])
    found = re.search(
        name + r"\s+(?:is|is actually)\s+(?:an?\s+)?(\w+)[ -]type", text, re.I
    )
    return bool(
        found
        and found.group(1).casefold() not in [t.casefold() for t in facts["types"]]
    )


def asserts_claim(text, claim):
    body = normalized(text)
    value = normalized(claim)
    index = body.find(value)
    if index < 0:
        return False
    before = body[max(0, index - 100) : index].strip()
    after = body[index + len(value) :].strip()
    if re.search(
        r"(?:falsely claim|false claim|incorrect claim|wrong claim|not true that)(?: that)?$",
        before,
    ):
        return False
    if re.match(
        r"(?:(?:but|which|that|this)\s+)?(?:(?:statement|claim)\s+)?(?:is\s+)?(?:false|incorrect|untrue|wrong|not true)\b",
        after,
    ):
        return False
    return True


class Rounds:
    def __init__(self, storage, knowledge, clock=time.monotonic):
        self.storage = storage
        self.knowledge = knowledge
        self.clock = clock
        self.sessions = {}
        self.locks = {}
        self.ticks = {}
        self.rng = secrets.SystemRandom()

    def persist(self, s):
        self.storage.save("_sessions", s["sessionId"], s)

    def load(self, sid):
        if sid not in self.sessions:
            s = self.storage.load("_sessions", sid)
            if not s:
                raise HTTPException(
                    404,
                    "This saved round is unavailable on this computer. Start a new party.",
                )
            s["_running"] = False
            if s["status"] not in TERMINAL:
                s["status"] = "paused"
            s["_awaitingPlayback"] = False
            s["_epoch"] += 1
            self.sessions[sid] = s
        self.locks.setdefault(sid, asyncio.Lock())
        self.ticks.setdefault(sid, self.clock())
        s = self.sessions[sid]
        self.tick(s)
        return s

    def tick(self, s):
        now = self.clock()
        last = self.ticks.get(s["sessionId"], now)
        self.ticks[s["sessionId"]] = now
        if (
            s["_running"]
            and s["timerRemaining"] is not None
            and s["status"] not in TERMINAL
        ):
            s["timerRemaining"] = max(0, s["timerRemaining"] - max(0, now - last))
            if s["timerRemaining"] <= 0:
                self.finish(
                    s,
                    "lost",
                    "Time ran out before all victory conditions were complete.",
                )

    def finish(self, s, status, reason):
        s["status"] = status
        s["resultReason"] = reason
        s["_running"] = False
        s["_epoch"] += 1
        s["_awaitingPlayback"] = False
        self.persist(s)

    def victory(self, s):
        lines = rules.bingo_lines(s["marked"])
        s["completedLines"] = len(lines)
        enough = len(lines) >= s["requiredLines"]
        eliminated = all(
            role != "impostor" or bid in s["eliminated"]
            for bid, role in s["_roles"].items()
        )
        if enough and (s["mode"] != "impostor" or eliminated):
            self.finish(
                s,
                "won",
                "Required bingo lines completed"
                + (
                    " and every impostor eliminated."
                    if s["mode"] == "impostor"
                    else "."
                ),
            )

    def public(self, s):
        self.tick(s)
        fields = (
            "sessionId",
            "mode",
            "topic",
            "category",
            "pool",
            "board",
            "marked",
            "flagged",
            "bots",
            "relationships",
            "relationshipLocks",
            "subject",
            "lastChaos",
            "status",
            "requiredLines",
            "completedLines",
            "timerRemaining",
            "eliminated",
            "resultReason",
            "polls",
            "forceNextSubject",
        )
        result = {k: copy.deepcopy(s[k]) for k in fields}
        result["messages"] = [
            {k: copy.deepcopy(m.get(k)) for k in PUBLIC_MESSAGE if k in m}
            for m in s["messages"]
        ]
        result["settings"] = copy.deepcopy(s["settings"])
        result["running"] = s["_running"]
        result["awaitingPlayback"] = s["_awaitingPlayback"]
        result["generating"] = self.locks[s["sessionId"]].locked()
        result["questionQueue"] = [q["botId"] for q in s["_questions"]]
        result["pollPending"] = s["_pollPending"]
        result["impostorCount"] = (
            2
            if s["mode"] == "impostor" and len(s["bots"]) == 6
            else 1
            if s["mode"] == "impostor"
            else 0
        )
        result["remainingImpostors"] = result["impostorCount"] - len(s["eliminated"])
        # Only eliminated impostors are revealed. No roles, evidence or lies are serialized.
        result["revealedRoles"] = {bid: "impostor" for bid in s["eliminated"]}
        return result

    def create(self, state, settings):
        bots = copy.deepcopy(state.get("bots", []))
        board = state.get("board", [])
        pool = validated_pool(state.get("pool", []))
        if not 3 <= len(bots) <= 6 or len({b.get("id") for b in bots}) != len(bots):
            raise ValueError("Choose 3–6 distinct bots.")
        if any(
            not all(
                isinstance(b.get(k), str) and b[k].strip()
                for k in ("id", "name", "description", "personality", "color")
            )
            for b in bots
        ):
            raise ValueError(
                "Every bot needs a name, personality, description and color."
            )
        if (
            len(board) != 25
            or any(not isinstance(n, str) or not n.strip() for n in board)
            or len({rules.normalize(n) for n in board}) != 25
        ):
            raise ValueError("Fill all 25 squares with unique nonempty entries.")
        if not pool or not state.get("topic", "").strip():
            raise ValueError("Choose a topic and a valid topic pool.")
        mode = state.get("mode", "normal")
        if mode not in MODES:
            raise ValueError("Choose Normal, Chaos or Impostor mode.")
        required = int(state.get("requiredLines", 1))
        if not 1 <= required <= 12:
            raise ValueError("Required bingo lines must be between 1 and 12.")
        if mode == "impostor" and not any(
            self.knowledge.false_claim(state["topic"], p["name"]) for p in pool
        ):
            raise ValueError(
                "Impostor mode needs known factual profiles. Choose Pokémon/ZZZ or import sourced profiles with types or faction facts."
            )
        timer = (
            float(settings.get("timerSeconds", 300))
            if settings.get("timerEnabled")
            else None
        )
        if timer is not None and (not math.isfinite(timer) or timer <= 0):
            raise ValueError("The timer duration must be positive.")
        relationships = {}
        locks = {}
        ids = {b["id"] for b in bots}
        for key, value in state.get("relationships", {}).items():
            if set(key.split("|")) <= ids and len(key.split("|")) == 2:
                relationships[key] = max(-100, min(100, int(value)))
                locks[key] = bool(state.get("relationshipLocks", {}).get(key, False))
        sid = uuid.uuid4().hex
        roles = (
            roles_for(bots, self.rng)
            if mode == "impostor"
            else {b["id"]: "innocent" for b in bots}
        )
        s = {
            "sessionId": sid,
            "mode": mode,
            "topic": state["topic"].strip(),
            "category": state.get("category", "Characters"),
            "pool": pool,
            "board": [n.strip() for n in board],
            "marked": [
                bool(settings.get("free") and i == 12 and board[i] == "FREE")
                for i in range(25)
            ],
            "flagged": [False] * 25,
            "bots": bots,
            "messages": [],
            "relationships": relationships,
            "relationshipLocks": locks,
            "subject": "",
            "lastChaos": None,
            "status": "paused",
            "requiredLines": required,
            "completedLines": 0,
            "timerRemaining": timer,
            "eliminated": [],
            "resultReason": "",
            "polls": [],
            "forceNextSubject": False,
            "settings": copy.deepcopy(settings),
            "_roles": roles,
            "_mentions": [],
            "_deceptions": [],
            "_questions": [],
            "_pollPending": False,
            "_lastPollTurn": 0,
            "_running": False,
            "_epoch": 0,
            "_awaitingPlayback": False,
            "_startingRelationships": copy.deepcopy(relationships),
            "_requests": {},
        }
        # Auto-mark and eligible-square hints conflict with the new trust rules.
        s["settings"]["autoMark"] = False
        s["settings"]["detect"] = False
        self.sessions[sid] = s
        self.locks[sid] = asyncio.Lock()
        self.ticks[sid] = self.clock()
        self.persist(s)
        return self.public(s)

    def active_bots(self, s):
        return [b for b in s["bots"] if b["id"] not in s["eliminated"]]

    def control(self, sid, action):
        s = self.load(sid)
        if s["status"] in TERMINAL:
            if action in ("start", "reset_timer"):
                raise ValueError("This round has ended. Replay or start a new party.")
            return self.public(s)
        if action == "start":
            s["_running"] = True
            s["status"] = (
                "generating"
                if self.locks[sid].locked()
                else "waiting_for_speaker"
                if s["settings"].get("manualSpeaker") and not s["_questions"]
                else "playing"
            )
        elif action in ("pause", "restore"):
            s["_running"] = False
            s["status"] = "paused"
            if action == "restore":
                s["_awaitingPlayback"] = False
        elif action == "stop":
            s["_running"] = False
            s["status"] = "paused"
            s["_epoch"] += 1
            s["_awaitingPlayback"] = False
        elif action == "complete":
            s["_awaitingPlayback"] = False
            s["status"] = (
                "paused"
                if not s["_running"]
                else "waiting_for_speaker"
                if s["settings"].get("manualSpeaker")
                and not s["_questions"]
                and not s["_pollPending"]
                else "playing"
            )
        elif action == "force_subject":
            s["forceNextSubject"] = not s["forceNextSubject"]
        elif action == "accusation_open":
            s["status"] = "accusation_pending"
        elif action == "accusation_close":
            s["status"] = "playing" if s["_running"] else "paused"
        else:
            raise ValueError("Unknown playback action.")
        self.ticks[sid] = self.clock()
        self.persist(s)
        return self.public(s)

    def settings(self, sid, settings, bots=None, relationships=None, locks=None):
        s = self.load(sid)
        # Timer, board rules and mode are setup-only; runtime/audio choices remain editable.
        allowed = {
            "url",
            "model",
            "temperature",
            "maxTokens",
            "memory",
            "sentences",
            "thinking",
            "weights",
            "speed",
            "clashes",
            "intensity",
            "showRelations",
            "manualSpeaker",
            "pollsEnabled",
            "transitionWeights",
            "chaosFrequency",
            "showChaos",
            "tts",
            "engine",
            "rate",
            "volume",
            "pitch",
            "autoSpeak",
            "stopOnPause",
            "sounds",
            "animations",
            "reduced",
            "fontSize",
            "scale",
        }
        s["settings"].update({k: v for k, v in settings.items() if k in allowed})
        if not s["settings"].get("pollsEnabled"):
            s["_pollPending"] = False
        if bots is not None:
            if [b.get("id") for b in bots] != [b["id"] for b in s["bots"]]:
                raise ValueError("Crew IDs cannot change during a round.")
            s["bots"] = copy.deepcopy(bots)
        if relationships is not None:
            for key, value in relationships.items():
                if key in {
                    pair(a["id"], b["id"])
                    for a in s["bots"]
                    for b in s["bots"]
                    if a != b
                }:
                    s["relationships"][key] = max(-100, min(100, int(value)))
        if locks is not None:
            s["relationshipLocks"].update(locks)
        self.persist(s)
        return self.public(s)

    def mark(self, sid, index):
        s = self.load(sid)
        if s["status"] in TERMINAL:
            return self.public(s)
        if not 0 <= index < 25:
            raise ValueError("Invalid square.")
        if s["settings"].get("free") and index == 12 and s["board"][index] == "FREE":
            return self.public(s)
        if s["marked"][index]:
            s["marked"][index] = False
        else:
            name = s["board"][index]
            safe = any(
                m["entry"] == name
                and (s["mode"] != "impostor" or m["role"] == "innocent")
                for m in s["_mentions"]
            )
            if not safe:
                self.finish(
                    s,
                    "lost",
                    "That entry had not been mentioned by an innocent bot."
                    if s["mode"] == "impostor"
                    else "That entry had not been mentioned by a bot.",
                )
            else:
                s["marked"][index] = True
                self.victory(s)
        self.persist(s)
        return self.public(s)

    def accuse(self, sid, index, bot_id):
        s = self.load(sid)
        if s["mode"] != "impostor":
            raise ValueError("Accusations are only available in Impostor mode.")
        if s["status"] in TERMINAL:
            return self.public(s)
        if not 0 <= index < 25 or bot_id not in s["_roles"]:
            raise ValueError("Choose a valid square and suspect.")
        if bot_id in s["eliminated"]:
            raise ValueError("This impostor was already eliminated.")
        correct = s["_roles"][bot_id] == "impostor" and any(
            m["entry"] == s["board"][index] and m["botId"] == bot_id and m["deceptive"]
            for m in s["_mentions"]
        )
        if not correct:
            self.finish(
                s,
                "lost",
                "The accusation did not identify an impostor who deceptively mentioned this entry.",
            )
        else:
            s["flagged"][index] = True
            s["eliminated"].append(bot_id)
            s["_questions"] = [q for q in s["_questions"] if q["botId"] != bot_id]
            s["status"] = "playing" if s["_running"] else "paused"
            self.victory(s)
        self.persist(s)
        return self.public(s)

    def record_mentions(self, s, message, deception=None):
        found = rules.board_mentions(message["message"], s["pool"], s["board"])
        deceptive_mentions = (
            rules.board_mentions(deception["text"], s["pool"], s["board"])
            if deception
            else {}
        )
        message["mentionedEntities"] = list(found)
        for name, canonical in found.items():
            s["_mentions"].append(
                {
                    "entry": name,
                    "botId": message["botId"],
                    "messageId": message["id"],
                    "timestamp": message["createdAt"],
                    "role": s["_roles"][message["botId"]],
                    "deceptive": name in deceptive_mentions,
                }
            )
        if deception:
            s["_deceptions"].append(
                {
                    "messageId": message["id"],
                    "botId": message["botId"],
                    "subject": message["subject"],
                    **deception,
                }
            )

    def question(self, sid, text, target):
        s = self.load(sid)
        if s["status"] in TERMINAL:
            raise ValueError("This round has ended.")
        text = validate_question(text)
        bots = self.active_bots(s)
        chosen = bots if target == "all" else [b for b in bots if b["id"] == target]
        if not chosen:
            raise ValueError("Choose an active bot or All bots.")
        if len(s["_questions"]) + len(chosen) > 12:
            raise ValueError("Wait for the queued questions to be answered first.")
        mid = uuid.uuid4().hex
        s["messages"].append(
            {
                "id": mid,
                "botId": "player",
                "name": "You",
                "color": "#c3b4e8",
                "personality": "Player",
                "message": text,
                "kind": "question",
                "createdAt": time.time(),
                "mentionedEntities": [],
            }
        )
        s["_questions"].extend(
            {"botId": b["id"], "question": text, "questionId": mid} for b in chosen
        )
        self.persist(s)
        return self.public(s)

    async def turn(self, sid, bot_id=None, request_id=None):
        s = self.load(sid)
        lock = self.locks[sid]
        if request_id and request_id in s["_requests"]:
            return self.public(s)
        if lock.locked():
            raise HTTPException(
                409, "A turn or poll is already generating for this round."
            )
        if s["status"] in TERMINAL:
            raise ValueError("This round has ended.")
        if s["_awaitingPlayback"]:
            raise HTTPException(
                409,
                "Finish or skip the current message before requesting another turn.",
            )
        async with lock:
            epoch = s["_epoch"]
            settings = copy.deepcopy(s["settings"])
            bots = self.active_bots(s)
            dialogue = [
                m for m in s["messages"] if m.get("kind", "dialogue") == "dialogue"
            ]
            last = dialogue[-1] if dialogue else None
            question = s["_questions"][0] if s["_questions"] else None
            if settings.get("manualSpeaker") and not bot_id and not question:
                raise ValueError(
                    "Choose the next speaker or RANDOM before generating a turn."
                )
            selected = (
                question["botId"]
                if question
                else None
                if bot_id == "random"
                else bot_id
            )
            if selected:
                bot = next((b for b in bots if b["id"] == selected), None)
                if not bot:
                    raise ValueError("Choose an active bot.")
                if not question and last and last["botId"] == selected:
                    raise ValueError("Choose a different bot for the next turn.")
            else:
                bot = rules.speaker(bots, last["botId"] if last else None, self.rng)
            action = rules.direction(settings.get("weights", [40, 25, 35]), self.rng)
            role = s["_roles"][bot["id"]]
            if role == "impostor" and not s["forceNextSubject"] and not question:
                action = self.rng.choices(
                    ["continue", "respond", "new_subject"], [65, 25, 10]
                )[0]
            current = s["subject"]
            obsessed = (
                sum(
                    current in m.get("mentionedEntities", [])
                    or m.get("subject") == current
                    for m in dialogue[-6:]
                )
                >= 4
                if current
                else False
            )
            if s["forceNextSubject"] or (obsessed and self.rng.random() < 0.85):
                action = "new_subject"
            subject = (
                select_subject(
                    s["topic"],
                    current,
                    s["pool"],
                    dialogue,
                    self.knowledge,
                    settings.get("transitionWeights"),
                    s["forceNextSubject"],
                    self.rng,
                )
                if action == "new_subject" or not current
                else current
            )
            deception = None
            if (
                role == "impostor"
                and self.rng.random() < 0.4
                and not any(d["subject"] == subject for d in s["_deceptions"][-8:])
            ):
                deception = self.knowledge.false_claim(s["topic"], subject)
                if deception is None:
                    eligible = [
                        e["name"]
                        for e in s["pool"]
                        if self.knowledge.false_claim(s["topic"], e["name"])
                    ]
                    if eligible and not s["forceNextSubject"]:
                        subject = select_subject(
                            s["topic"],
                            current,
                            [e for e in s["pool"] if e["name"] in eligible],
                            dialogue,
                            self.knowledge,
                            settings.get("transitionWeights"),
                            False,
                            self.rng,
                        )
                        if subject != current:
                            action = "new_subject"
                        deception = self.knowledge.false_claim(s["topic"], subject)
            event = (
                rules.chaos_event(
                    settings.get("chaosFrequency", "medium"), s["lastChaos"], self.rng
                )
                if s["mode"] == "chaos"
                else None
            )
            memory = max(2, min(40, int(settings.get("memory", 12))))
            facts = self.knowledge.facts(s["topic"], subject)
            reply = (
                question["questionId"]
                if question
                else last["id"]
                if action == "respond" and last
                else None
            )
            relationships = (
                [
                    {
                        "bot": b["name"],
                        "score": s["relationships"].get(pair(bot["id"], b["id"]), 0),
                    }
                    for b in bots
                    if b["id"] != bot["id"]
                ]
                if settings.get("clashes", True)
                else []
            )
            system = f"You are {bot['name']}. Personality: {bot['description']}. Discuss {s['topic']} ({s['category']}) in {max(2, min(4, int(settings.get('sentences', 3))))} short sentences. Speak only for yourself. Be natural, not a host. Opinions may differ; factual claims must respect the provided sourced facts. When facts are unknown, do not invent profiles. No game mechanics or role disclosures. Do not copy other speakers' catchphrases or add unrelated taglines. Use varied transitions without a fixed opening. Return JSON with message and stance (agree/disagree/neutral toward the last speaker)."
            if deception:
                system += (
                    " For this hidden-role turn, convincingly include this deliberately incorrect sentence exactly once: "
                    + deception["text"]
                    + " Do not admit it is a lie. Surround it with natural personality-driven dialogue."
                )
            elif role == "impostor":
                system += " Express a convincing subjective opinion; do not reveal your secret role."
            if question:
                system += " Answer the player’s opinion question directly in your own personality. Do not force an unrelated subject into the answer unless a next-subject change was explicitly requested."
            question_pool = self.knowledge.collection(s["topic"]) or rules.unique_pool(
                next(
                    (
                        v
                        for k, v in rules.POOLS.items()
                        if rules.normalize(k) == rules.normalize(s["topic"])
                    ),
                    s["pool"],
                )
            )
            question_facts = (
                [
                    self.knowledge.facts(s["topic"], n)
                    for n in rules.mentions(question["question"], question_pool)[:4]
                ]
                if question
                else []
            )
            context = {
                "subject": subject,
                "action": action,
                "knownFacts": facts,
                "previousSubject": current,
                "transitionConnection": self.knowledge.facts(s["topic"], current)
                if action == "new_subject"
                else None,
                "recentDialogue": [
                    {"speaker": m["name"], "message": m["message"]}
                    for m in dialogue[-memory:]
                ],
                "relationshipContext": relationships,
                "chaosEvent": event,
                "question": question["question"] if question else None,
                "questionFacts": question_facts,
                "earlierSubjects": list(
                    dict.fromkeys(m.get("subject", "") for m in dialogue[:-memory])
                )[-8:],
                "replyTo": next(
                    (m["name"] for m in s["messages"] if m["id"] == reply), None
                ),
                "roster": [b["name"] for b in bots],
                "recentPollResults": [
                    {
                        "question": p["question"],
                        "options": p["options"],
                        "totals": p["totals"],
                    }
                    for p in s["polls"][-2:]
                ],
            }
            s["status"] = "generating" if s["_running"] else "paused"
            self.persist(s)
            try:
                for attempt in range(2):
                    data = await generate(
                        {
                            **settings,
                            "repeatPenalty": 1.12,
                            "seed": self.rng.randrange(2**31),
                        },
                        system,
                        json.dumps(context, ensure_ascii=False),
                        TURN_SCHEMA,
                    )
                    text = rules.clean_response(data.get("message", ""))
                    reason = repetition_reason(text, dialogue)
                    if re.search(
                        r"\b(?:i am|i'm|my role is|my hidden role is)\s+(?:an? |the )?(?:impostor|innocent)\b",
                        text,
                        re.I,
                    ):
                        reason = "Do not disclose or discuss your game role. Stay in character and discuss the selected subject."
                    if (
                        not reason
                        and (not question or s["forceNextSubject"])
                        and subject not in rules.mentions(text, s["pool"])
                    ):
                        reason = "Discuss the selected subject explicitly in this turn."
                    overused = [
                        n
                        for n in rules.mentions(text, s["pool"])
                        if n != subject
                        and sum(
                            n in m.get("mentionedEntities", []) for m in dialogue[-8:]
                        )
                        >= 4
                    ]
                    if not reason and overused and not question:
                        reason = (
                            "Stop adding the overused unrelated subject "
                            + ", ".join(overused)
                            + ". Focus on the selected subject instead."
                        )
                    if (
                        not reason
                        and deception
                        and not asserts_claim(text, deception["text"])
                    ):
                        reason = "Include the required sentence exactly as supplied, without revealing the role."
                    if (
                        not reason
                        and not deception
                        and any(
                            factual_conflict(text, self.knowledge.facts(s["topic"], n))
                            for n in rules.mentions(text, s["pool"])
                        )
                    ):
                        reason = "The response contradicts the verified types. Correct the factual claim."
                    if not reason:
                        break
                    context["qualityCorrection"] = (
                        reason
                        + " Produce a fresh angle, different sentence structure and different joke. Keep the same selected subject."
                    )
                else:
                    raise ValueError(
                        "The model kept repeating or contradicting the selected facts after one quality retry. Resume to try a new turn."
                    )
                self.tick(s)
                if (
                    s["_epoch"] != epoch
                    or s["status"] in TERMINAL
                    or bot["id"] in s["eliminated"]
                ):
                    return self.public(s)
                if question and not s["forceNextSubject"] and not deception:
                    spoken_subjects = rules.mentions(text, s["pool"])
                    if spoken_subjects:
                        subject = spoken_subjects[0]
                message = {
                    "id": uuid.uuid4().hex,
                    "botId": bot["id"],
                    "name": bot["name"],
                    "personality": bot["personality"],
                    "color": bot["color"],
                    "message": text,
                    "subject": subject,
                    "conversationAction": "question" if question else action,
                    "chaosEvent": event,
                    "replyToMessageId": reply,
                    "questionId": question["questionId"] if question else None,
                    "kind": "dialogue",
                    "createdAt": time.time(),
                }
                self.record_mentions(s, message, deception)
                s["messages"].append(message)
                s["subject"] = subject
                s["lastChaos"] = event or s["lastChaos"]
                if question:
                    s["_questions"].pop(0)
                if (
                    settings.get("clashes", True)
                    and last
                    and last["botId"] != bot["id"]
                ):
                    key = pair(bot["id"], last["botId"])
                    if not s["relationshipLocks"].get(key):
                        s["relationships"][key] = rules.relationship(
                            s["relationships"].get(key, 0),
                            data.get("stance", "neutral"),
                            float(settings.get("intensity", 1)),
                        )
                if s["forceNextSubject"] and subject != current:
                    s["forceNextSubject"] = False
                turn_count = len(dialogue) + 1
                if (
                    settings.get("pollsEnabled")
                    and turn_count - s["_lastPollTurn"] >= 6
                    and self.rng.random() < 0.15
                ):
                    s["_pollPending"] = True
                s["_awaitingPlayback"] = True
                s["status"] = "playing" if s["_running"] else "paused"
                if request_id:
                    s["_requests"][request_id] = message["id"]
                self.persist(s)
                return self.public(s)
            except Exception:
                if s["status"] not in TERMINAL:
                    s["_running"] = False
                    s["status"] = "paused"
                    self.persist(s)
                raise

    async def poll(self, sid):
        s = self.load(sid)
        lock = self.locks[sid]
        if not s["settings"].get("pollsEnabled"):
            raise ValueError("Bot polls are disabled.")
        if s["status"] in TERMINAL or s["_awaitingPlayback"] or lock.locked():
            raise HTTPException(
                409, "Polls wait until the current message and speech have finished."
            )
        if not s["_pollPending"]:
            raise ValueError("No poll is scheduled yet.")
        async with lock:
            epoch = s["_epoch"]
            bots = self.active_bots(s)
            creator = self.rng.choice(bots)
            proposal = await generate(
                s["settings"],
                "Create one open-ended opinion poll about the selected subject. Return JSON question and 2–4 distinct options. No bingo mechanics.",
                json.dumps(
                    {
                        "topic": s["topic"],
                        "subject": s["subject"],
                        "previousPolls": [p["question"] for p in s["polls"][-5:]],
                        "creatorPersonality": creator["description"],
                    }
                ),
                POLL_SCHEMA,
            )
            question = proposal.get("question", "")
            options = proposal.get("options", [])
            if (
                not isinstance(question, str)
                or not 2 <= len(options) <= 4
                or any(not isinstance(o, str) or not o.strip() for o in options)
                or len(set(options)) != len(options)
            ):
                raise ValueError(
                    "The model returned an invalid poll. Resume to try again."
                )
            validate_question(question)
            if any(
                SequenceMatcher(
                    None, normalized(question), normalized(p["question"])
                ).ratio()
                >= 0.8
                for p in s["polls"][-8:]
            ):
                s["_pollPending"] = False
                s["_lastPollTurn"] = len(
                    [m for m in s["messages"] if m.get("kind") == "dialogue"]
                )
                self.persist(s)
                return self.public(s)
            votes = []
            for bot in bots:
                if not s["settings"].get("pollsEnabled"):
                    return self.public(s)
                vote = await generate(
                    s["settings"],
                    f"You are {bot['name']}: {bot['description']}. Choose exactly one option according to your personality; provide a brief opinion. Do not invent facts or discuss game roles.",
                    json.dumps(
                        {
                            "question": question,
                            "options": [
                                {"index": i, "label": o} for i, o in enumerate(options)
                            ],
                            "facts": self.knowledge.facts(s["topic"], s["subject"]),
                            "relationships": {
                                b["name"]: s["relationships"].get(
                                    pair(bot["id"], b["id"]), 0
                                )
                                for b in bots
                                if b != bot
                            },
                        }
                    ),
                    VOTE_SCHEMA,
                )
                option = vote.get("option")
                explanation = vote.get("explanation")
                if (
                    type(option) is not int
                    or not 0 <= option < len(options)
                    or not isinstance(explanation, str)
                ):
                    raise ValueError(
                        "A poll vote was invalid. No incomplete poll was saved."
                    )
                explanation = rules.clean_response(explanation, max_length=2000)
                votes.append(
                    {
                        "botId": bot["id"],
                        "name": bot["name"],
                        "option": option,
                        "explanation": explanation,
                    }
                )
            self.tick(s)
            if (
                s["_epoch"] != epoch
                or s["status"] in TERMINAL
                or not s["settings"].get("pollsEnabled")
            ):
                return self.public(s)
            votes = [v for v in votes if v["botId"] not in s["eliminated"]]
            poll = {
                "id": uuid.uuid4().hex,
                "creatorId": creator["id"],
                "creatorName": creator["name"],
                "question": question,
                "options": options,
                "votes": votes,
                "totals": [
                    sum(v["option"] == i for v in votes) for i in range(len(options))
                ],
            }
            s["polls"].append(poll)
            s["_pollPending"] = False
            s["_lastPollTurn"] = len(
                [m for m in s["messages"] if m.get("kind") == "dialogue"]
            )
            self.record_mentions(
                s,
                {
                    "id": poll["id"],
                    "botId": creator["id"],
                    "message": question,
                    "subject": s["subject"],
                    "createdAt": time.time(),
                },
            )
            for vote in votes:
                m = {
                    "id": uuid.uuid4().hex,
                    "botId": vote["botId"],
                    "message": vote["explanation"],
                    "subject": s["subject"],
                    "createdAt": time.time(),
                }
                self.record_mentions(s, m)
            self.persist(s)
            return self.public(s)

    def save(self, sid, name):
        s = self.load(sid)
        self.persist(s)
        self.storage.save("_round_saves", name, copy.deepcopy(s))

    def fork(self, sid):
        original = self.load(sid)
        saved = copy.deepcopy(original)
        saved["sessionId"] = uuid.uuid4().hex
        saved["_running"] = False
        saved["_awaitingPlayback"] = False
        saved["_epoch"] = 0
        saved["_requests"] = {}
        if saved["status"] not in TERMINAL:
            saved["status"] = "paused"
        key = saved["sessionId"]
        self.sessions[key] = saved
        self.locks[key] = asyncio.Lock()
        self.ticks[key] = self.clock()
        self.persist(saved)
        return self.public(saved)

    def restore_save(self, name):
        saved = self.storage.load("_round_saves", name)
        if not saved:
            raise ValueError("Saved round not found.")
        saved["sessionId"] = uuid.uuid4().hex
        saved["_running"] = False
        saved["_awaitingPlayback"] = False
        saved["_epoch"] += 1
        if saved["status"] not in TERMINAL:
            saved["status"] = "paused"
        self.sessions[saved["sessionId"]] = saved
        self.locks[saved["sessionId"]] = asyncio.Lock()
        self.ticks[saved["sessionId"]] = self.clock()
        self.persist(saved)
        return self.public(saved)

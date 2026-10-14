"""Lightweight checks over actual dialogue, with bounded regeneration in the engine."""

from collections import Counter
from difflib import SequenceMatcher
import re


def words(text):
    return re.findall(r"[\w']+", text.casefold())


def normalized(text):
    return " ".join(words(text))


def repetition_reason(text: str, recent: list[dict]) -> str | None:
    value = normalized(text)
    if not value:
        return "The reply contains no dialogue."
    sentences = [normalized(s) for s in re.split(r"[.!?]+", text) if len(words(s)) >= 7]
    prior = [
        m.get("message", "")
        for m in recent[-14:]
        if m.get("kind", "dialogue") == "dialogue"
    ]
    grams = Counter()
    for old in prior:
        old_value = normalized(old)
        if value == old_value:
            return "This repeats a recent message exactly."
        if (
            min(len(words(text)), len(words(old))) >= 8
            and SequenceMatcher(None, value, old_value).ratio() >= 0.83
        ):
            return "This is nearly identical to a recent message."
        old_sentences = [
            normalized(s) for s in re.split(r"[.!?]+", old) if len(words(s)) >= 7
        ]
        if any(
            SequenceMatcher(None, a, b).ratio() >= 0.86
            for a in sentences
            for b in old_sentences
        ):
            return "A sentence copies a recent sentence with small changes."
        tokens = words(old)
        grams.update(
            set(tuple(tokens[i : i + 5]) for i in range(max(0, len(tokens) - 4)))
        )
    tokens = words(text)
    if any(
        grams[tuple(tokens[i : i + 5])] >= 2 for i in range(max(0, len(tokens) - 4))
    ):
        return "This reuses a catchphrase already used by several bots."
    return None


def subject_weight(name: str, messages: list[dict]) -> float:
    count = sum(
        name in m.get("mentionedEntities", []) or m.get("subject") == name
        for m in messages[-10:]
    )
    return 1 / (1 + count * count)

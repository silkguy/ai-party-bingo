"""Validated collections and fresh offline sampling, separate from the board."""

import random
import secrets
from .rules import normalize, unique_pool, POOLS
from .ollama import generate, token_budget

POOL_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entries"],
    "additionalProperties": False,
}
PLACEHOLDERS = {
    "name",
    "names",
    "character",
    "character name",
    "entity",
    "example",
    "unknown",
    "n/a",
    "placeholder",
    "string",
    "subject",
    "actual name",
    "your name",
}


def validated(entries):
    if not isinstance(entries, list):
        raise ValueError("The generated entries must be a JSON list.")
    clean = unique_pool(entries)
    return [
        {**e, "aliases": [a for a in e["aliases"] if normalize(a) not in PLACEHOLDERS]}
        for e in clean
        if normalize(e["name"]) not in PLACEHOLDERS
    ]


def sample(collection, previous=None, locked=None, count=60, rng=random):
    collection = validated(collection)
    previous = set(previous or [])
    locked = validated(locked or [])
    names = {e["name"] for e in collection}
    if any(e["name"] not in names for e in locked):
        raise ValueError("A locked entry is not in the available collection.")
    locked_names = {e["name"] for e in locked}
    fresh = [e for e in collection if e["name"] not in previous | locked_names]
    old = [
        e for e in collection if e["name"] in previous and e["name"] not in locked_names
    ]
    rng.shuffle(fresh)
    rng.shuffle(old)
    return (locked + fresh + old)[: max(count, len(locked))]


class TopicPools:
    def __init__(self, storage, knowledge):
        self.storage = storage
        self.knowledge = knowledge

    async def get(self, topic, category, settings, regenerate=False, locked=None):
        topic = " ".join(topic.split())
        category = " ".join(category.split())
        if not topic:
            raise ValueError("Enter a discussion topic before generating its pool.")
        if not category:
            raise ValueError("Enter a category, such as Characters or Species.")
        key = self.knowledge.topic_key(topic) + "|" + normalize(category)
        previous = self.storage.load("pool_selection", key) or []
        collection = self.knowledge.collection(topic, category)
        if collection is not None and not collection:
            raise ValueError(
                "No local entries match these topic/category filters. Broaden the category or generation instead of inventing names."
            )
        source = "Full offline Pokédex" if collection else ""
        if collection is None:
            curated = next(
                (v for k, v in POOLS.items() if normalize(k) == normalize(topic)), None
            )
            if curated and normalize(category) == "characters":
                collection = unique_pool(curated)
                source = "Curated local character collection"
        if collection is None:
            collection = validated(
                self.storage.load("pool_collection", key)
                or self.storage.load("pool", key)
                or []
            )
            source = "Cached AI collection — review entries for accuracy"
            exhausted = self.storage.load("pool_exhausted", key)
            if not collection or (
                regenerate and len(collection) < 120 and not exhausted
            ):
                for attempt in range(2):
                    try:
                        data = await generate(
                            {
                                **settings,
                                "maxTokens": max(
                                    4096, int(settings.get("maxTokens", 768))
                                ),
                            },
                            "Return real known names for the topic as JSON. Each name must be an actual entity, not a placeholder or a field label. Never invent characters. Return fewer entries if the category is small.",
                            f"Topic: {topic}. Category: {category}. Give up to 70 distinct entries. Expand beyond these existing names when possible: {[e['name'] for e in collection][:120]}. Fresh sampling seed: {secrets.token_hex(5)}. Attempt {attempt + 1}.",
                            POOL_SCHEMA,
                        )
                        new = validated(data.get("entries", []))
                    except (ValueError, TypeError, AttributeError):
                        continue
                    if new:
                        before = len(collection)
                        collection = validated(collection + new)
                        if before and len(collection) == before:
                            self.storage.save("pool_exhausted", key, True)
                        break
                else:
                    if not collection:
                        raise ValueError(
                            "Ollama returned no real names after two attempts. Import your own list or broaden the category; placeholders such as “name” are rejected."
                        )
                self.storage.save("pool_collection", key, collection)
        if (
            not regenerate
            and len(validated(previous)) >= min(25, len(collection))
            and not locked
            and {e["name"] for e in validated(previous)}
            <= {e["name"] for e in collection}
        ):
            selection = validated(previous)
        else:
            selection = sample(collection, [e["name"] for e in previous], locked)
        self.storage.save("pool_selection", key, selection)
        return {
            "entries": selection,
            "count": len(selection),
            "collectionCount": len(collection),
            "source": source,
            "warning": "The available collection is small, so some regeneration overlap is unavoidable."
            if len(collection) <= len(selection)
            else None,
        }

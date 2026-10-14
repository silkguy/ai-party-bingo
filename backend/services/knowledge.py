"""Local, source-attributed facts. Model-generated profiles never become verified facts."""

import csv
import io
import json
import re
from pathlib import Path
from .rules import normalize

DATA = Path(__file__).resolve().parent.parent / "data"
FACTIONS = {
    "Cunning Hares": ["Anby Demara", "Nicole Demara", "Billy Kid", "Nekomiya Mana"],
    "Victoria Housekeeping": [
        "Ellen Joe",
        "Von Lycaon",
        "Alexandrina Sebastiane",
        "Corin Wickes",
    ],
    "Belobog Heavy Industries": [
        "Koleda Belobog",
        "Ben Bigger",
        "Anton Ivanov",
        "Grace Howard",
    ],
    "Sons of Calydon": [
        "Caesar King",
        "Burnice White",
        "Lucy",
        "Piper Wheel",
        "Lighter",
    ],
    "Criminal Investigation Special Response Team": [
        "Zhu Yuan",
        "Qingyi",
        "Seth Lowell",
    ],
    "Hollow Special Operations Section 6": [
        "Tsukishiro Yanagi",
        "Hoshimi Miyabi",
        "Asaba Harumasa",
        "Soukaku",
    ],
}
ZZZ = {
    "Ellen Joe": {
        "attribute": "Ice",
        "role": "Attack",
        "facts": [
            "A shark Thiren with a shark tail.",
            "Works as a maid in Victoria Housekeeping.",
            "Often appears sleepy; fights with large shears.",
        ],
    },
    "Nicole Demara": {
        "attribute": "Ether",
        "role": "Support",
        "facts": [
            "Leader of the Cunning Hares.",
            "Often short on money; cares about her team.",
        ],
    },
    "Anby Demara": {
        "attribute": "Electric",
        "role": "Stun",
        "facts": [
            "Reserved member of the Cunning Hares.",
            "Known for her interest in movies and burgers.",
        ],
    },
    "Billy Kid": {
        "attribute": "Physical",
        "role": "Attack",
        "facts": [
            "A sentient robot in the Cunning Hares.",
            "Enthusiastic fan of Starlight Knights; uses guns.",
        ],
    },
    "Nekomiya Mana": {
        "attribute": "Physical",
        "role": "Attack",
        "facts": ["A cat Thiren, also called Nekomata."],
    },
    "Von Lycaon": {
        "attribute": "Ice",
        "role": "Stun",
        "facts": ["A wolf Thiren who works as a refined butler."],
    },
    "Alexandrina Sebastiane": {
        "attribute": "Electric",
        "role": "Support",
        "facts": ["Also called Rina; a maid in Victoria Housekeeping."],
    },
    "Corin Wickes": {
        "attribute": "Physical",
        "role": "Attack",
        "facts": ["A shy maid who fights using a large circular saw."],
    },
}


class Knowledge:
    def __init__(self, storage):
        self.storage = storage
        data = json.loads((DATA / "pokedex.json").read_text(encoding="utf-8"))
        self.pokemon = data["entries"]
        self.pokemon_by_id = {p["id"]: p for p in self.pokemon}
        self.pokemon_by_name = {normalize(p["name"]): p for p in self.pokemon}
        self.source = data

    def is_pokemon(self, topic):
        return normalize(topic).startswith(
            (
                "pokémon",
                "pokemon",
                "pokémon characters",
                "pokemon characters",
                "pokedex",
                "pokédex",
            )
        )

    def topic_key(self, topic):
        return (
            normalize(topic).replace("pokémon", "pokemon").replace("pokédex", "pokedex")
        )

    def collection(self, topic, category="Characters"):
        if self.is_pokemon(topic):
            kind = normalize(category)
            if kind == "abilities":
                return [
                    {"name": name, "aliases": []}
                    for name in sorted(
                        {a for p in self.pokemon for a in p["abilities"]}
                    )
                ]
            if kind == "types":
                return [
                    {"name": name, "aliases": []}
                    for name in sorted({t for p in self.pokemon for t in p["types"]})
                ]
            if kind in ("movies", "games", "locations", "items", "moves", "episodes"):
                return None
            text = normalize(topic + " " + category)
            types = {t for p in self.pokemon for t in p["types"]}
            filter_types = {
                t
                for t in types
                if re.search(r"(?<!\w)" + re.escape(t.casefold()) + r"(?!\w)", text)
            }
            generation = re.search(r"\bgen(?:eration)?\s*(\d{1,2})\b", text)
            starters = {
                1,
                4,
                7,
                25,
                133,
                152,
                155,
                158,
                252,
                255,
                258,
                387,
                390,
                393,
                495,
                498,
                501,
                650,
                653,
                656,
                722,
                725,
                728,
                810,
                813,
                816,
                906,
                909,
                912,
            }
            candidates = [
                p
                for p in self.pokemon
                if (not filter_types or filter_types.intersection(p["types"]))
                and (not generation or p["generation"] == int(generation.group(1)))
                and ("starter" not in text or p["id"] in starters)
            ]
            return [{"name": p["name"], "aliases": p["aliases"]} for p in candidates]
        return None

    def facts(self, topic, name):
        imported = self.storage.load("knowledge", self.topic_key(topic)) or {}
        if normalize(name) in imported and (
            not self.is_pokemon(topic) or normalize(name) not in self.pokemon_by_name
        ):
            return imported[normalize(name)]
        if self.is_pokemon(topic):
            p = self.pokemon_by_name.get(normalize(name))
            if p:
                family = [
                    q["name"]
                    for q in self.pokemon
                    if q["evolutionChain"] == p["evolutionChain"] and q["id"] != p["id"]
                ]
                return {
                    "name": p["name"],
                    "types": p["types"],
                    "abilities": p["abilities"],
                    "generation": p["generation"],
                    "species": p["species"],
                    "evolutionFamily": family,
                    "source": "PokeAPI pinned offline species dataset",
                }
        if "zenless" in normalize(topic):
            result = {
                "name": name,
                **ZZZ.get(name, {}),
                "source": "Curated ZZZ launch/base-agent facts; factions from official character profiles",
            }
            for faction, members in FACTIONS.items():
                if name in members:
                    result.update(
                        faction=faction, teammates=[n for n in members if n != name]
                    )
            if len(result) > 2:
                return result
        return {
            "name": name,
            "source": "No verified local profile. Avoid factual guesses; express opinions or uncertainty.",
        }

    def related(self, topic, current, candidates):
        facts = self.facts(topic, current)
        strong = set(facts.get("evolutionFamily", []) + facts.get("teammates", []))
        types = set(facts.get("types", []))
        weak = []
        for name in candidates:
            other = self.facts(topic, name)
            if types.intersection(other.get("types", [])) or (
                facts.get("attribute")
                and facts.get("attribute") == other.get("attribute")
            ):
                weak.append(name)
        return [n for n in candidates if n in strong], weak

    def false_claim(self, topic, name):
        facts = self.facts(topic, name)
        if facts.get("types"):
            wrong = next(
                t
                for t in [
                    "Water",
                    "Fire",
                    "Grass",
                    "Electric",
                    "Ice",
                    "Dragon",
                    "Fairy",
                    "Ghost",
                    "Normal",
                ]
                if t not in facts["types"]
            )
            return {
                "text": f"{name} is a {wrong}-type Pokémon.",
                "truth": facts["types"],
                "field": "types",
                "falseValue": wrong,
            }
        if facts.get("faction"):
            wrong = next(f for f in FACTIONS if f != facts["faction"])
            return {
                "text": f"{name} belongs to {wrong}.",
                "truth": facts["faction"],
                "field": "faction",
                "falseValue": wrong,
            }
        return None

    def import_profiles(self, topic, content, format):
        if not topic.strip():
            raise ValueError("Choose a topic for the imported profiles.")
        if format not in ("csv", "json"):
            raise ValueError("Knowledge imports support JSON or CSV.")
        if format == "csv":
            profiles = list(csv.DictReader(io.StringIO(content)))
            for p in profiles:
                for field in ("types", "facts", "aliases", "teammates"):
                    if field in p:
                        p[field] = [v.strip() for v in p[field].split("|") if v.strip()]
        else:
            parsed = json.loads(content)
            profiles = parsed.get("entries", []) if isinstance(parsed, dict) else parsed
        if not isinstance(profiles, list) or len(profiles) > 5000:
            raise ValueError("Import a list of at most 5000 factual profiles.")
        result = self.storage.load("knowledge", self.topic_key(topic)) or {}
        for p in profiles:
            if (
                not isinstance(p, dict)
                or not isinstance(p.get("name"), str)
                or not p["name"].strip()
            ):
                raise ValueError("Every knowledge profile needs a nonempty name.")
            if not p.get("source"):
                raise ValueError(
                    "Every imported profile needs a source; imported facts are user-provided, not independently verified."
                )
            for field in (
                "types",
                "abilities",
                "facts",
                "teammates",
                "evolutionFamily",
            ):
                if field in p and (
                    not isinstance(p[field], list)
                    or any(
                        not isinstance(value, str) or not value.strip()
                        for value in p[field]
                    )
                ):
                    raise ValueError(
                        f"{field} must be a list of nonempty strings (CSV uses | between values)."
                    )
            if "faction" in p and (
                not isinstance(p["faction"], str) or not p["faction"].strip()
            ):
                raise ValueError("Faction must be a nonempty string.")
            allowed = {
                k: v
                for k, v in p.items()
                if k
                in (
                    "name",
                    "types",
                    "abilities",
                    "generation",
                    "species",
                    "faction",
                    "attribute",
                    "role",
                    "facts",
                    "teammates",
                    "evolutionFamily",
                    "source",
                )
            }
            result[normalize(p["name"])] = allowed
        self.storage.save("knowledge", self.topic_key(topic), result)
        return len(result)

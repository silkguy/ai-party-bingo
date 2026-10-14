"""Build the bundled offline Pokédex from a pinned BSD-licensed PokeAPI snapshot."""

import csv
import io
import json
from pathlib import Path
from urllib.request import urlopen

COMMIT = "81d20919845b6a445969b9265aab5cec6b04cece"
BASE = f"https://raw.githubusercontent.com/PokeAPI/pokeapi/{COMMIT}/"
ROOT = Path(__file__).resolve().parent.parent


def rows(name):
    print("Reading " + name, flush=True)
    with urlopen(BASE + "data/v2/csv/" + name, timeout=60) as response:
        return list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))


def main():
    species = rows("pokemon_species.csv")
    names = {
        int(r["pokemon_species_id"]): r
        for r in rows("pokemon_species_names.csv")
        if r["local_language_id"] == "9"
    }
    pokemon = {
        int(r["species_id"]): int(r["id"])
        for r in rows("pokemon.csv")
        if r["is_default"] == "1"
    }
    type_names = {
        r["type_id"]: r["name"]
        for r in rows("type_names.csv")
        if r["local_language_id"] == "9"
    }
    ability_names = {
        r["ability_id"]: r["name"]
        for r in rows("ability_names.csv")
        if r["local_language_id"] == "9"
    }
    types = {}
    abilities = {}
    for r in rows("pokemon_types.csv"):
        types.setdefault(int(r["pokemon_id"]), []).append(type_names[r["type_id"]])
    for r in rows("pokemon_abilities.csv"):
        abilities.setdefault(int(r["pokemon_id"]), []).append(
            ability_names[r["ability_id"]]
        )
    entries = []
    for r in species:
        sid = int(r["id"])
        pid = pokemon.get(sid)
        if sid not in names or pid is None:
            continue
        name = names[sid]["name"]
        entries.append(
            {
                "id": sid,
                "name": name,
                "aliases": list(
                    dict.fromkeys(
                        [r["identifier"].replace("-", " "), name.replace("’", "'")]
                    )
                ),
                "types": types.get(pid, []),
                "abilities": abilities.get(pid, []),
                "generation": int(r["generation_id"]),
                "species": names[sid]["genus"],
                "evolvesFrom": int(r["evolves_from_species_id"])
                if r["evolves_from_species_id"]
                else None,
                "evolutionChain": int(r["evolution_chain_id"]),
            }
        )
    dataset = {
        "source": "PokeAPI",
        "commit": COMMIT,
        "license": "BSD-3-Clause (repository license); Pokémon names/game facts are attributed to their respective owners",
        "speciesCount": len(entries),
        "entries": entries,
    }
    target = ROOT / "backend/data"
    target.mkdir(exist_ok=True)
    (target / "pokedex.json").write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    with urlopen(BASE + "LICENSE.md", timeout=30) as response:
        (target / "POKEAPI_LICENSE.md").write_bytes(response.read())
    print(f"Bundled {len(entries)} species. No network is needed during play.")


if __name__ == "__main__":
    main()

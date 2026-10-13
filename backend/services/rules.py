"""Pure game rules. The board never enters a dialogue prompt."""
import random
import re
import unicodedata

PERSONALITIES = {
    'Nerd': 'Enthusiastic detail lover; explains lore, corrects errors, sometimes overexplains.',
    'Hater': 'Opinionated critic, skeptical and frequently disagrees, without cruelty.',
    'Fan': 'Excitable fan who passionately defends favorites.',
    'Troll': 'Playfully teases others and starts harmless arguments.',
    'Serious': 'Formal, factual and impatient with unnecessary jokes.',
    'Clueless': 'Asks unusual questions and misunderstands details in funny ways.',
    'Contrarian': 'Challenges popular opinions and takes unexpected positions.',
    'Shy': 'Hesitant and gentle; occasionally defends an unpopular opinion.',
    'Dramatic': 'Exaggerates reactions and treats small disagreements like grand events.',
    'Chaotic': 'Makes strange but relevant connections and unexpected observations.',
}
CHAOS = ['Sudden argument', 'Unpopular opinion', 'Random ranking', 'Unexpected defense',
         'Personality switch', 'Group debate', 'Random obsession', 'Unexpected topic change',
         'Friendly roast', 'Alliance']
POOLS = {
 'Zenless Zone Zero': ['Anby Demara','Nicole Demara','Billy Kid','Nekomiya Mana','Ellen Joe','Von Lycaon','Alexandrina Sebastiane','Corin Wickes','Koleda Belobog','Ben Bigger','Anton Ivanov','Grace Howard','Soldier 11','Zhu Yuan','Qingyi','Seth Lowell','Jane Doe','Caesar King','Burnice White','Lucy','Piper Wheel','Lighter','Tsukishiro Yanagi','Hoshimi Miyabi','Asaba Harumasa','Soukaku','Astra Yao','Evelyn Chevalier','Pulchra','Trigger','Soldier 0 Anby'],
 'Pokémon': ['Pikachu','Bulbasaur','Ivysaur','Venusaur','Charmander','Charmeleon','Charizard','Squirtle','Wartortle','Blastoise','Caterpie','Butterfree','Weedle','Beedrill','Pidgey','Pidgeot','Rattata','Raichu','Sandshrew','Clefairy','Vulpix','Ninetales','Jigglypuff','Zubat','Oddish','Psyduck','Growlithe','Abra','Machop','Geodude','Gengar','Onix','Eevee','Snorlax','Mewtwo','Mew'],
 'Genshin Impact': ['Amber','Kaeya','Lisa','Jean','Diluc','Venti','Klee','Albedo','Eula','Mona','Fischl','Bennett','Razor','Barbara','Noelle','Sucrose','Diona','Rosaria','Xiangling','Xingqiu','Chongyun','Ningguang','Beidou','Zhongli','Xiao','Ganyu','Hu Tao','Keqing','Qiqi','Yelan','Shenhe','Raiden Shogun','Nahida','Furina'],
 'Honkai: Star Rail': ['March 7th','Dan Heng','Himeko','Welt','Kafka','Silver Wolf','Blade','Jing Yuan','Jingliu','Seele','Bronya','Gepard','Serval','Pela','Sampo','Natasha','Clara','Hook','Asta','Arlan','Herta','Bailu','Yanqing','Tingyun','Qingque','Sushang','Luocha','Fu Xuan','Topaz','Guinaifen','Huohuo','Argenti','Ruan Mei','Dr. Ratio','Sparkle','Acheron','Aventurine','Robin','Firefly'],
}
def normalize(s: str) -> str:
    return unicodedata.normalize('NFKC', s).casefold().strip()
def unique_pool(entries: list) -> list[dict]:
    result, seen = [], set()
    for item in entries:
        if isinstance(item, str):
            parts = [p.strip() for p in item.split('|')]
            item = {'name': parts[0], 'aliases': parts[1:]}
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            continue
        name = item['name'].strip()[:100]
        if not name or normalize(name) in seen:
            continue
        seen.add(normalize(name))
        aliases = item.get('aliases', [])
        result.append({'name': name, 'aliases': [a.strip()[:100] for a in aliases if isinstance(a,str) and a.strip()] if isinstance(aliases,list) else []})
    return result[:500]
def mentions(text: str, pool: list[dict]) -> list[str]:
    aliases: dict[str, set[str]] = {}
    for item in pool:
        terms = [item['name'], *item.get('aliases', [])]
        if len(item['name'].split()) > 1:
            terms.append(item['name'].split()[0])
        for term in terms:
            aliases.setdefault(normalize(term), set()).add(item['name'])
    found = set()
    for term, owners in aliases.items():
        if len(owners) == 1 and re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', normalize(text)):
            found.update(owners)
    return [p['name'] for p in pool if p['name'] in found]
def bingo_lines(marked: list[bool]) -> list[list[int]]:
    lines = [[r*5+c for c in range(5)] for r in range(5)] + [[r*5+c for r in range(5)] for c in range(5)] + [[i*6 for i in range(5)], [4+i*4 for i in range(5)]]
    return [line for line in lines if len(marked)==25 and all(marked[i] for i in line)]
def spin(rng=random) -> int:
    return rng.choice([3,4,5,6])
def speaker(bots: list, last: str | None, rng=random) -> dict:
    return rng.choice([b for b in bots if b['id'] != last])
def direction(weights: list[float], rng=random) -> str:
    if len(weights)!=3 or any(w<0 for w in weights) or sum(weights)<=0:
        raise ValueError('Direction weights must be nonnegative and sum to more than zero.')
    return rng.choices(['continue','respond','new_subject'], weights=weights)[0]
def chaos_event(frequency: str, previous: str | None, rng=random) -> str | None:
    chance = {'off':0,'low':.05,'medium':.15,'high':.30}.get(frequency,0)
    return rng.choice([e for e in CHAOS if e != previous]) if rng.random()<chance else None
def relationship(score: int, stance: str, intensity: float) -> int:
    return max(-100, min(100, score + round({'agree':6,'disagree':-8,'neutral':0}.get(stance,0)*intensity)))
def clean_response(text: str, max_length: int = 6000) -> str:
    if not isinstance(text, str):
        raise ValueError('Ollama returned a non-text final response.')
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S | re.I)
    unfinished = re.search(r'<think>', text, flags=re.I)
    if unfinished:
        text = text[:unfinished.start()]
    text = text.strip()
    if not text:
        raise ValueError('Ollama returned no final answer (it may have used the token budget for thinking).')
    if len(text) > max_length:
        raise ValueError(f'Ollama returned a final response longer than {max_length} characters.')
    return text

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

app=FastAPI(title='AI Bingo Party — local API')
storage=Storage()
turn_lock=asyncio.Lock()
class Request(BaseModel):
    settings: dict = Field(default_factory=dict)
    state: dict = Field(default_factory=dict)
    topic: str = ''
    category: str = 'Characters'
    regenerate: bool = False

@app.get('/api/catalog')
async def catalog():
    return {'personalities':rules.PERSONALITIES,'topics':list(rules.POOLS),'chaos':rules.CHAOS}
@app.post('/api/spin')
async def spin(): return {'count':rules.spin()}
@app.post('/api/health')
async def health(req: Request):
    try:
        async with httpx.AsyncClient(timeout=5,trust_env=False) as client:
            response=await client.get(req.settings.get('url','http://localhost:11434').rstrip('/')+'/api/tags')
            response.raise_for_status()
        models=[m['name'] for m in response.json().get('models',[])]
        name=req.settings.get('model','qwen3:4b')
        return {'ok':name in models,'models':models,'message':'Ready for a local party.' if name in models else f"Model '{name}' is not downloaded. Run: ollama pull {name}, wait for completion, then retry. Or choose a downloaded model in Settings > AI."}
    except Exception:
        return {'ok':False,'models':[],'message':'Cannot reach Ollama. Install Ollama, run ollama serve, then ollama pull qwen3:4b. Check your server URL and retry.'}
@app.post('/api/pool')
async def pool(req: Request):
    key=req.topic.casefold()+'|'+req.category.casefold()
    cached=storage.load('pool',key)
    if cached and not req.regenerate: return {'entries':cached,'source':'Local cache'}
    if req.topic in rules.POOLS and req.category.casefold() in ('characters','pokémon','pokemon'):
        entries=rules.unique_pool(rules.POOLS[req.topic]); source='Curated local dataset (not exhaustive)'
    else:
        try:
            data=await generate(req.settings,'Return JSON only: {"entries":[{"name":"name","aliases":[]}]}. Include only real, known entries, no invented names.',f'List 45 distinct {req.category} for {req.topic}. If fewer exist return fewer. No guessing.',True)
            entries=rules.unique_pool(data.get('entries',[])); source='AI generated — review names for accuracy'
        except Exception as exc: raise HTTPException(502,str(exc))
    if not entries: raise HTTPException(422,'No valid entries returned. Import your own list or retry.')
    storage.save('pool',key,entries)
    return {'entries':entries,'source':source}
@app.post('/api/generate/{kind}')
async def ideas(kind: str, req: Request):
    prompts={'personality':'Invent one funny, distinctive personality. Return {"name":"short label","description":"two sentences"}.', 'topics':'Suggest eight discussion topics for a character bingo party. Return {"topics":["topic"]}.'}
    if kind not in prompts: raise HTTPException(404,'Unknown generator')
    try: return await generate(req.settings,'Return valid JSON only.',prompts[kind],True)
    except Exception as exc: raise HTTPException(502,str(exc))
@app.post('/api/turn')
async def turn(req: Request):
    if turn_lock.locked(): raise HTTPException(409,'A turn is already generating. Please wait.')
    async with turn_lock:
        s=req.state; settings=req.settings
        bots=s.get('bots',[]); pool=rules.unique_pool(s.get('pool',[])); history=s.get('messages',[])
        if not 3<=len(bots)<=6 or not pool: raise HTTPException(422,'Set up 3–6 bots and a nonempty topic pool first.')
        try:
            bot=rules.speaker(bots,history[-1]['botId'] if history else None)
            action=rules.direction(settings.get('weights',[40,25,35]))
            subject=s.get('subject') if action!='new_subject' else None
            subject=subject if subject in [p['name'] for p in pool] else random.choice(pool)['name']
            event=rules.chaos_event(settings.get('chaos','off'),s.get('lastChaos'))
            recent=history[-int(settings.get('memory',12)):]
            target=history[-1]['botId'] if history else None
            relations=s.get('relationships',{}) if settings.get('clashes',True) else {}
            system=f"You are {bot['name']}. Personality: {bot['description']}. Discuss {s.get('topic')}, category {s.get('category')}. Use {settings.get('sentences',3)} short sentences. Stay in character and on topic. Respond to recent messages, avoid repetition, introductions and role labels. Never speak for others or mention game mechanics. Return JSON: {{\"message\":\"your dialogue\",\"stance\":\"agree/disagree/neutral\"}}. Stance describes your response to the latest speaker."
            prompt=json.dumps({'subject':subject,'direction':action,'recent':[{ 'speaker':m['name'],'message':m['message']} for m in recent], 'relationships':relations,'roster':[{ 'id':b['id'],'name':b['name']} for b in bots],'earlierSubjects':list(dict.fromkeys(m['subject'] for m in history[:-int(settings.get('memory',12))]))[-8:],'event':event,'instructions':'If personality switch, reverse your usual behavior for this turn only. Keep all events harmless.'})
            data=await generate(settings,system,prompt,TURN_SCHEMA)
            message=rules.clean_response(data.get('message',''))
            if settings.get('clashes',True) and target:
                key='|'.join(sorted([bot['id'],target]))
                relations[key]=rules.relationship(relations.get(key,0),data.get('stance','neutral'),float(settings.get('intensity',1)))
            return {'botId':bot['id'],'name':bot['name'],'personality':bot['personality'],'color':bot['color'],'subject':subject,'conversationAction':action,'message':message,'mentionedEntities':rules.mentions(message,rules.unique_pool([*pool,*[n for n in s.get('board',[]) if n and n!='FREE']])),'chaosEvent':event,'relationships':relations}
        except Exception as exc: raise HTTPException(502,'Local generation failed: '+str(exc))
@app.get('/api/saves/{kind}')
async def list_saves(kind: str): return storage.list(kind)
@app.get('/api/saves/{kind}/{name}')
async def load(kind: str,name: str):
    value=storage.load(kind,name)
    if value is None: raise HTTPException(404,'Save not found')
    return value
@app.put('/api/saves/{kind}/{name}')
async def save(kind: str,name: str,value: dict):
    storage.save(kind,name,value); return {'ok':True}
@app.get('/api/voices')
async def voices():
    root=Path(os.getenv('PIPER_VOICE_DIR','voices'))
    return {'piperAvailable':bool(piper_command()),'voices':[p.stem for p in root.glob('*.onnx') if p.with_suffix('.onnx.json').exists()],'labels':VOICE_LABELS}
class Speech(BaseModel):
    text: str = Field(max_length=6000)
    voice: str
    rate: float = Field(default=1,ge=.5,le=2)
@app.post('/api/speech')
async def speech(req: Speech):
    root=Path(os.getenv('PIPER_VOICE_DIR','voices')).resolve()
    model=root/(req.voice+'.onnx')
    command=piper_command()
    if model.parent!=root or not model.exists() or not model.with_suffix('.onnx.json').exists() or not command:
        raise HTTPException(503,'Piper voice unavailable; select an installed browser voice.')
    key=hashlib.sha256((req.text+req.voice+str(req.rate)).encode()).hexdigest()
    cache=storage.path/'audio'; cache.mkdir(exist_ok=True); path=cache/(key+'.wav')
    if not path.exists():
        def render():
            subprocess.run([*command,'--model',str(model),'--output_file',str(path),'--length_scale',str(1/req.rate)],input=req.text,text=True,check=True,timeout=60,capture_output=True)
        try: await asyncio.to_thread(render)
        except Exception:
            path.unlink(missing_ok=True)
            raise HTTPException(503,'Piper failed. Browser speech fallback is available.')
        files=sorted(cache.glob('*.wav'),key=lambda p:p.stat().st_mtime)
        for old in files[:-100]: old.unlink(missing_ok=True)
    return FileResponse(path,media_type='audio/wav')

frontend=Path(__file__).resolve().parent.parent/'frontend'/'dist'
if frontend.exists(): app.mount('/',StaticFiles(directory=frontend,html=True),name='frontend')

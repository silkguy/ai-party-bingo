import asyncio
import importlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def module(tmp_path,monkeypatch):
    monkeypatch.setenv('BINGO_DATA_DIR',str(tmp_path))
    import backend.main
    return importlib.reload(backend.main)

def setup_state():
    return {'topic':'Pokémon','category':'Characters','pool':[{'name':'Pikachu','aliases':[]}],
            'board':['DO_NOT_PASS_TO_MODEL']*25,
            'bots':[{'id':str(i),'name':'Bot '+str(i),'description':'Nerd','personality':'Nerd','color':'#fff'} for i in range(3)],
            'messages':[],'relationships':{}}

def test_api_save_load_health(module,monkeypatch):
    with TestClient(module.app) as client:
        assert client.post('/api/spin').json()['count'] in [3,4,5,6]
        assert client.put('/api/saves/game/test',json={'state':{'marked':[True]}}).status_code==200
        assert client.get('/api/saves/game/test').json()['state']['marked']==[True]
        assert client.get('/api/saves/game/missing').status_code==404
        assert client.post('/api/pool',json={'topic':'Pokémon'}).json()['source'].startswith('Curated')
        assert client.post('/api/health',json={'settings':{'url':'http://127.0.0.1:1'}}).json()['ok'] is False

def test_turn_metadata_and_board_secrecy(module,monkeypatch):
    async def fake(settings,system,prompt,structured):
        assert 'DO_NOT_PASS_TO_MODEL' not in system+prompt
        return {'message':'Pikachu is delightful. I love the ears.','stance':'agree','botId':'invented','mentionedEntities':['fake']}
    monkeypatch.setattr(module,'generate',fake)
    with TestClient(module.app) as client:
        result=client.post('/api/turn',json={'state':setup_state()}).json()
        assert result['botId'] in ['0','1','2']
        assert result['mentionedEntities']==['Pikachu']
        assert result['chaosEvent'] is None

def test_invalid_json_response(module,monkeypatch):
    async def fake(*args):return {'message':'<think>hidden</think>'}
    monkeypatch.setattr(module,'generate',fake)
    with TestClient(module.app) as client:
        assert client.post('/api/turn',json={'state':setup_state()}).status_code==502

@pytest.mark.asyncio
async def test_overlapping_turns(module,monkeypatch):
    started=asyncio.Event();release=asyncio.Event()
    async def fake(*args):
        started.set();await release.wait();return {'message':'Pikachu is here.'}
    monkeypatch.setattr(module,'generate',fake)
    request=module.Request(state=setup_state())
    first=asyncio.create_task(module.turn(request));await started.wait()
    with pytest.raises(module.HTTPException) as error:await module.turn(request)
    assert error.value.status_code==409
    release.set();await first

def test_built_frontend_is_served(module):
    with TestClient(module.app) as client:
        response=client.get('/')
        assert response.status_code==200
        assert 'AI Bingo Party' in response.text
        assert '/assets/' in response.text

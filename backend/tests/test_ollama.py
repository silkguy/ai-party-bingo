import httpx
import pytest
from backend.services import ollama

@pytest.mark.asyncio
@pytest.mark.parametrize('error,expected',[
    ("model 'qwen3:4b' not found", 'ollama pull qwen3:4b'),
    ('404 page not found', 'server URL'),
])
async def test_missing_model_is_distinguished_from_missing_endpoint(monkeypatch,error,expected):
    original=httpx.AsyncClient
    transport=httpx.MockTransport(lambda request:httpx.Response(404,json={'error':error}))
    monkeypatch.setattr(ollama.httpx,'AsyncClient',lambda **kwargs:original(transport=transport,**kwargs))
    with pytest.raises(ValueError,match=expected):
        await ollama.generate({},'system','prompt')


def mock_responses(monkeypatch, replies):
    import json
    calls=[]
    original=httpx.AsyncClient
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json=replies[min(len(calls)-1,len(replies)-1)])
    transport=httpx.MockTransport(respond)
    monkeypatch.setattr(ollama.httpx,'AsyncClient',lambda **kwargs:original(transport=transport,**kwargs))
    return calls

@pytest.mark.asyncio
async def test_thinking_only_response_retries_final_answer_without_leaking_reasoning(monkeypatch):
    calls=mock_responses(monkeypatch,[
        {'message':{'content':'','thinking':'SECRET INTERNAL REASONING'},'done_reason':'length'},
        {'message':{'content':'{"message":"Ellen has a great design.","stance":"neutral"}'}},
    ])
    result=await ollama.generate({'maxTokens':300,'thinking':True},'Be Nova','Discuss Ellen',ollama.TURN_SCHEMA)
    assert result['message']=='Ellen has a great design.'
    assert len(calls)==2 and calls[0]['think'] is True and calls[1]['think'] is False
    assert calls[1]['messages'][1]['content'].endswith('/no_think')
    assert calls[1]['options']['num_predict']>calls[0]['options']['num_predict']
    assert 'SECRET' not in str(result)+str(calls)

@pytest.mark.asyncio
async def test_default_uses_api_flag_and_qwen_no_think_instruction(monkeypatch):
    calls=mock_responses(monkeypatch,[{'message':{'content':'{"message":"Hello.","stance":"agree"}'}}])
    assert (await ollama.generate({},'System','Context',ollama.TURN_SCHEMA))['message']=='Hello.'
    assert len(calls)==1 and calls[0]['think'] is False
    assert calls[0]['messages'][1]['content'].endswith('/no_think')
    assert calls[0]['format']==ollama.TURN_SCHEMA

@pytest.mark.asyncio
@pytest.mark.parametrize('first_content',[
    '{"message":"incomplete',
    '{"message":""}',
    '{"dialogue":"Wrong field"}',
    '<think>internal but no final answer</think>',
    '{"message":"'+'x'*6001+'"}',
])
async def test_invalid_final_answer_recovers_once(monkeypatch,first_content):
    calls=mock_responses(monkeypatch,[{'message':{'content':first_content}}, {'message':{'content':'{"message":"A usable response."}'}}])
    result=await ollama.generate({},'System','Original subject/context',ollama.TURN_SCHEMA)
    assert result['message']=='A usable response.'
    assert result['stance']=='neutral'
    assert len(calls)==2
    assert all('Original subject/context' in c['messages'][1]['content'] for c in calls)

@pytest.mark.asyncio
async def test_retry_is_bounded_and_explains_exhausted_budget(monkeypatch):
    calls=mock_responses(monkeypatch,[{'message':{'content':'','thinking':'secret'},'done_reason':'length'}])
    with pytest.raises(ValueError,match='after one automatic retry.*token limit'):
        await ollama.generate({},'System','Prompt',ollama.TURN_SCHEMA)
    assert len(calls)==2

@pytest.mark.asyncio
async def test_topic_lists_can_exceed_short_dialogue_character_limit(monkeypatch):
    import json
    entries=[{'name':f'Entity {i}', 'aliases':['Alternative name '+str(i)]} for i in range(150)]
    calls=mock_responses(monkeypatch,[{'message':{'content':json.dumps({'entries':entries})}}])
    result=await ollama.generate({},'System','List entities',True)
    assert len(result['entries'])==150
    assert calls[0]['options']['num_predict']>=2048

@pytest.mark.parametrize('content',[
    '```json\n{"message":"Valid dialogue."}\n```',
    '<THINK>secret</THINK>{"message":"Valid dialogue."}',
])
def test_structured_wrapper_handling(content):
    result=ollama.parse_final({'message':{'content':content}},ollama.TURN_SCHEMA)
    assert result['message']=='Valid dialogue.'

@pytest.mark.parametrize('requested',[0,-1,50,'bad',None])
def test_small_or_invalid_saved_token_budgets_are_safe(requested):
    assert ollama.token_budget({'maxTokens':requested},ollama.TURN_SCHEMA)>=512

@pytest.mark.asyncio
async def test_missing_model_is_not_retried(monkeypatch):
    calls=[]
    original=httpx.AsyncClient
    def respond(request):
        calls.append(request)
        return httpx.Response(404,json={'error':"model 'qwen3:4b' not found"})
    transport=httpx.MockTransport(respond)
    monkeypatch.setattr(ollama.httpx,'AsyncClient',lambda **kwargs:original(transport=transport,**kwargs))
    with pytest.raises(ValueError,match='ollama pull qwen3:4b'):
        await ollama.generate({},'System','Prompt',ollama.TURN_SCHEMA)
    assert len(calls)==1

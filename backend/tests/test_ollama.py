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

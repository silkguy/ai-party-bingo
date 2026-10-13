import json
import httpx
from .rules import clean_response

async def generate(settings: dict, system: str, prompt: str, structured=False):
    payload={'model':settings.get('model','qwen3:4b'), 'stream':False,
             'think':settings.get('thinking',False),
             'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
             'options':{'temperature':settings.get('temperature',.85),'num_predict':settings.get('maxTokens',300)}}
    if structured: payload['format']='json'
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        response=await client.post(settings.get('url','http://localhost:11434').rstrip('/')+'/api/chat',json=payload)
        if response.status_code==404:
            try:
                detail=response.json().get('error','')
            except (ValueError, AttributeError):
                detail=''
            if 'model' in str(detail).casefold() and ('not found' in str(detail).casefold() or 'missing' in str(detail).casefold()):
                raise ValueError(f"Model '{payload['model']}' is not downloaded in Ollama. On this computer run: ollama pull {payload['model']}. Wait until it finishes, then Resume. You can also select an installed model in Settings > AI.")
            raise ValueError('Ollama chat endpoint was not found. Check the Ollama server URL in Settings > AI (normally http://localhost:11434).')
        response.raise_for_status()
        data=response.json()
    text=clean_response(data.get('message',{}).get('content',''))
    return json.loads(text) if structured else text

"""Local Ollama adapter with bounded recovery for missing/truncated final output."""

import copy
import json
import re
import httpx
from .rules import clean_response

TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "stance": {"type": "string", "enum": ["agree", "disagree", "neutral"]},
    },
    "required": ["message"],
    "additionalProperties": False,
}


def token_budget(settings: dict, structured: bool | dict) -> int:
    try:
        requested = int(settings.get("maxTokens", 768))
    except (TypeError, ValueError):
        requested = 768
    # A list of 45 named entities needs more room than one short dialogue turn.
    minimum = 2048 if structured is True else 512
    if settings.get("thinking", False):
        minimum = max(minimum, 2048)
    return min(8192, max(minimum, requested))


def parse_final(data: dict, structured: bool | dict):
    message = data.get("message")
    content = message.get("content", "") if isinstance(message, dict) else ""
    # message.thinking is intentionally never read as dialogue or exposed.
    text = clean_response(content, max_length=100000 if structured else 6000)
    if not structured:
        return text
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.I)
    if fenced:
        text = fenced.group(1)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Ollama returned a JSON value instead of an object.")
    if isinstance(structured, dict):
        for name in structured.get("required", []):
            if name not in parsed:
                raise ValueError("Ollama omitted a required response field: " + name)
        if structured.get("properties", {}).get("message"):
            parsed["message"] = clean_response(parsed.get("message", ""))
            if parsed.get("stance") not in ("agree", "disagree", "neutral"):
                parsed["stance"] = "neutral"
    return parsed


async def generate(
    settings: dict, system: str, prompt: str, structured: bool | dict = False
):
    thinking = bool(settings.get("thinking", False))
    final_only = " Return only the final answer. Do not include reasoning, analysis, or <think> tags."
    # Qwen3 also understands /no_think. Keep it in addition to the API flag,
    # because installed Ollama/model template versions differ.
    payload = {
        "model": settings.get("model", "qwen3:4b"),
        "stream": False,
        "think": thinking,
        "messages": [
            {"role": "system", "content": system + ("" if thinking else final_only)},
            {"role": "user", "content": prompt + ("" if thinking else "\n/no_think")},
        ],
        "options": {
            "temperature": settings.get("temperature", 0.85),
            "num_predict": token_budget(settings, structured),
            "repeat_penalty": settings.get("repeatPenalty", 1.1),
            **({"seed": settings["seed"]} if "seed" in settings else {}),
        },
    }
    if structured:
        payload["format"] = structured if isinstance(structured, dict) else "json"
    endpoint = settings.get("url", "http://localhost:11434").rstrip("/") + "/api/chat"
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        for attempt in range(2):
            response = await client.post(endpoint, json=payload)
            if response.status_code == 404:
                try:
                    detail = response.json().get("error", "")
                except (ValueError, AttributeError):
                    detail = ""
                if "model" in str(detail).casefold() and (
                    "not found" in str(detail).casefold()
                    or "missing" in str(detail).casefold()
                ):
                    raise ValueError(
                        f"Model '{payload['model']}' is not downloaded in Ollama. On this computer run: ollama pull {payload['model']}. Wait until it finishes, then Resume. You can also select an installed model in Settings > AI."
                    )
                raise ValueError(
                    "Ollama chat endpoint was not found. Check the Ollama server URL in Settings > AI (normally http://localhost:11434)."
                )
            response.raise_for_status()
            data = response.json()
            try:
                if not isinstance(data, dict):
                    raise ValueError("Ollama returned an unexpected response body.")
                return parse_final(data, structured)
            except (ValueError, TypeError) as error:
                if attempt == 1:
                    reason = (
                        "The model reached its generation token limit before finishing."
                        if isinstance(data, dict)
                        and data.get("done_reason") == "length"
                        else str(error)
                    )
                    raise ValueError(
                        "Ollama did not return a usable final answer after one automatic retry. "
                        + reason
                        + " In Settings > AI keep Enable thinking off; update Ollama if this continues, then press Resume."
                    ) from error
                # Retry only invalid final output, never connectivity/missing-model
                # failures. The same speaker, subject and context remain selected.
                payload = copy.deepcopy(payload)
                payload["think"] = False
                payload["options"]["num_predict"] = min(
                    8192, max(2048, payload["options"]["num_predict"] * 2)
                )
                payload["messages"][0]["content"] = system + final_only
                payload["messages"][1]["content"] = (
                    prompt
                    + "\nProduce the complete final answer now, with no explanations or reasoning.\n/no_think"
                )

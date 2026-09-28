"""OpenAI-compatible SSE streaming, with cancellation and provider fallback."""
import asyncio
import json
import logging
import httpx
from . import config

log = logging.getLogger(__name__)
active_provider = None
provider_errors = {}

async def provider_stream(provider, messages, tools=None):
    name, url, model, key = provider
    payload = dict(model=model, messages=messages, stream=True, temperature=0.6, max_tokens=400)
    if tools:
        payload.update(tools=tools, tool_choice='auto')
    async with httpx.AsyncClient(timeout=config.TIMEOUT) as client:
        async with client.stream('POST', url + '/chat/completions',
                                 headers={'Authorization': f'Bearer {key}'}, json=payload) as response:
            response.raise_for_status()
            lines = response.aiter_lines()
            while True:
                try:
                    line = await asyncio.wait_for(anext(lines), config.TIMEOUT)
                except StopAsyncIteration:
                    break
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    return
                event = json.loads(data)
                if event.get('error'):
                    raise RuntimeError('Provider stream error')
                choices = event.get('choices', [])
                if choices:
                    yield choices[0].get('delta', {})

async def chat_stream(messages, tools=None):
    """Yield text/tool events. Tools are emitted only after a complete stream.

    If a provider fails after yielding text, ask the next to continue that prefix.
    Already spoken text is never replayed. No side effects happen inside retries.
    """
    global active_provider
    prefix = ''
    for provider in config.PROVIDERS:
        name, _, _, key = provider
        if not key:
            continue
        attempt = list(messages)
        if prefix:
            attempt += [{'role': 'assistant', 'content': prefix}, {'role': 'user', 'content':
                'The connection dropped. Continue exactly where you stopped, without repeating any earlier words.'}]
        calls = {}
        got_output = False
        try:
            stream = provider_stream(provider, attempt, tools)
            try:
                while True:
                    try:
                        delta = await asyncio.wait_for(anext(stream), config.TIMEOUT)
                    except StopAsyncIteration:
                        break
                    active_provider = name
                    provider_errors.pop(name, None)
                    if delta.get('content'):
                        got_output = True
                        prefix += delta['content']
                        yield {'type': 'token', 'text': delta['content'], 'provider': name}
                    for part in delta.get('tool_calls', []):
                        call = calls.setdefault(part['index'], {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                        call['id'] += part.get('id', '')
                        for field in ('name', 'arguments'):
                            call['function'][field] += part.get('function', {}).get(field, '')
            finally:
                await stream.aclose()
            if not got_output and not calls:
                raise RuntimeError('Empty response')
            for call in calls.values():
                json.loads(call['function']['arguments'])
            if calls:
                yield {'type': 'tools', 'calls': list(calls.values()), 'provider': name}
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not log request bodies, keys, or private conversation text.
            reason = f'HTTP {exc.response.status_code}' if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
            provider_errors[name] = reason
            log.warning('%s unavailable: %s', name, reason)
            yield {'type': 'provider_fallback', 'provider': name, 'reason': reason}
    active_provider = None
    raise RuntimeError('No LLM is available. Configure a free Groq/NVIDIA key in backend/.env or start Ollama and pull the configured model.')

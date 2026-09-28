import asyncio
import pytest
from backend import llm

@pytest.mark.asyncio
async def test_fallback_and_prefix(monkeypatch):
    monkeypatch.setattr(llm.config, 'PROVIDERS', [('groq','','','x'), ('nvidia','','','x'), ('ollama','','','local')])
    seen = []
    async def stream(p, messages, tools=None):
        seen.append((p[0], messages))
        if p[0] == 'groq':
            yield {'content': 'Hello. '}
            raise TimeoutError()
        yield {'content': 'How are you?'}
    monkeypatch.setattr(llm, 'provider_stream', stream)
    events = [e async for e in llm.chat_stream([{'role':'user','content':'hi'}])]
    assert ''.join(e.get('text','') for e in events) == 'Hello. How are you?'
    assert seen[1][1][-2]['content'] == 'Hello. '
    assert llm.active_provider == 'nvidia'

@pytest.mark.asyncio
async def test_cancel_does_not_fallback(monkeypatch):
    async def stream(*args):
        raise asyncio.CancelledError()
        yield
    monkeypatch.setattr(llm, 'provider_stream', stream)
    with pytest.raises(asyncio.CancelledError):
        await anext(llm.chat_stream([]))

@pytest.mark.asyncio
async def test_missing_keys_and_all_failed(monkeypatch):
    monkeypatch.setattr(llm.config, 'PROVIDERS', [('groq','','',''), ('nvidia','','',''), ('ollama','','','local')])
    seen = []
    async def stream(p, *args):
        seen.append(p[0])
        raise ConnectionError()
        yield
    monkeypatch.setattr(llm, 'provider_stream', stream)
    with pytest.raises(RuntimeError, match='No LLM'):
        _ = [e async for e in llm.chat_stream([])]
    assert seen == ['ollama']

@pytest.mark.asyncio
async def test_tool_fragments(monkeypatch):
    async def stream(*args):
        yield {'tool_calls':[{'index':0,'id':'call_1','function':{'name':'action','arguments':'{"name":'}}]}
        yield {'tool_calls':[{'index':0,'function':{'arguments':'"google"}'}}]}
    monkeypatch.setattr(llm, 'provider_stream', stream)
    result = [e async for e in llm.chat_stream([])]
    assert result[-1]['calls'][0]['function']['arguments'] == '{"name":"google"}'

import json
import httpx
import pytest
from backend import config, speech

@pytest.mark.asyncio
async def test_shubh_stream_payload(monkeypatch):
    monkeypatch.setattr(config, 'SARVAM_API_KEY', 'test-key')
    monkeypatch.setattr(config, 'TTS_PROVIDER', 'sarvam')
    original = httpx.AsyncClient
    def handle(request):
        payload = json.loads(request.content)
        assert payload['speaker'] == 'shubh'
        assert payload['model'] == 'bulbul:v3'
        assert payload['language_code'] == 'hi-IN'
        assert payload['output_audio_codec'] == 'mp3'
        assert payload['pace'] == .9
        assert 'pitch' not in payload
        assert request.headers['api-subscription-key'] == 'test-key'
        return httpx.Response(200, content=b'mp3-audio')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    events = [event async for event in speech.tts_stream('नमस्ते।', 'hi', 'calm')]
    assert events == [{'type':'audio','data':b'mp3-audio'}]

@pytest.mark.asyncio
async def test_sarvam_missing_key(monkeypatch):
    monkeypatch.setattr(config, 'SARVAM_API_KEY', '')
    with pytest.raises(RuntimeError, match='SARVAM_API_KEY'):
        await anext(speech.sarvam_stream('Hello.'))

@pytest.mark.asyncio
async def test_sarvam_credit_error(monkeypatch):
    monkeypatch.setattr(config, 'SARVAM_API_KEY', 'test-key')
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: httpx.Response(403)), **kwargs))
    with pytest.raises(RuntimeError, match='credit balance'):
        await anext(speech.sarvam_stream('Hello.'))

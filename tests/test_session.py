import asyncio
import pytest
from backend.session import VoiceSession
from backend import session
from fastapi.testclient import TestClient
from backend.app import app

class Socket:
    def __init__(self): self.events = []
    async def send_json(self, data): self.events.append(data)

@pytest.mark.asyncio
async def test_interrupt_cancels_llm_and_tts_and_keeps_spoken(monkeypatch):
    llm_cancelled = asyncio.Event()
    tts_cancelled = asyncio.Event()
    async def fake_llm(*args, **kwargs):
        try:
            yield {'type': 'token', 'text': 'Hello there. More speech.'}
            await asyncio.sleep(60)
        finally: llm_cancelled.set()
    async def fake_tts(*args):
        try:
            yield {'type': 'boundary', 'text': 'Hello', 'offset': 0, 'duration': .3}
            yield {'type': 'boundary', 'text': 'there', 'offset': .3, 'duration': .3}
            yield {'type': 'audio', 'data': b'bytes'}
            await asyncio.sleep(60)
        finally: tts_cancelled.set()
    monkeypatch.setattr(session.llm, 'chat_stream', fake_llm)
    monkeypatch.setattr(session, 'tts_stream', fake_tts)
    ws = Socket(); voice = VoiceSession(ws)
    await voice.start(text='hi')
    for _ in range(100):
        if any(e['type'] == 'audio' for e in ws.events): break
        await asyncio.sleep(.001)
    await voice.message({'type':'playback','turn':voice.turn,'sentence':0,'seconds':.35})
    await asyncio.wait_for(voice.interrupt(), .3)
    assert llm_cancelled.is_set() and tts_cancelled.is_set()
    assert voice.history[-1]['content'] == 'Hello'
    previous = voice.turn - 1
    await voice.message({'type':'played','turn':previous,'sentence':0})
    assert voice.history[-1]['content'] == 'Hello'

def test_health_and_origin():
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    assert 'active_provider' in client.get('/health').json()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/voice', headers={'origin':'https://evil.example'}): pass
    with client.websocket_connect('/ws/voice', headers={'origin':'http://localhost:5173'}) as ws:
        assert ws.receive_json()['type'] == 'hello'
        ws.send_json({'type':'interrupt'})
        assert ws.receive_json()['state'] == 'LISTENING'

@pytest.mark.asyncio
async def test_audio_limits():
    ws = Socket(); voice = VoiceSession(ws)
    voice.recording = True
    await voice.receive_audio(b'x' * 65538)
    assert not voice.recording and not voice.audio
    assert ws.events[-1]['type'] == 'error'

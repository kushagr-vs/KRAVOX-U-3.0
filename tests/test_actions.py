import time
import pytest
from backend.actions import ActionRouter, validate
from backend import actions
from backend.session import VoiceSession
from test_session import Socket

@pytest.mark.asyncio
async def test_power_requires_fresh_spoken_confirmation(monkeypatch):
    calls = []
    async def job(name,args): calls.append((name,args)); return 'Submitted.'
    monkeypatch.setattr(actions, 'desktop_job', job)
    router = ActionRouter(VoiceSession(Socket()))
    assert 'Say yes' in await router.handle('power', {'action':'restart'})
    assert not calls
    assert 'microphone' in await router.confirm('yes', False)
    assert not calls
    assert await router.confirm('हाँ', True) == 'Submitted.'
    assert len(calls) == 1
    assert await router.confirm('yes', True) is None
    await router.handle('power', {'action':'shutdown'})
    router.pending['expires'] = time.monotonic()-1
    assert 'expired' in await router.confirm('yes', True)
    assert len(calls) == 1

@pytest.mark.asyncio
async def test_whatsapp_validates_and_can_cancel():
    router = ActionRouter(VoiceSession(Socket()))
    assert 'country code' in await router.handle('whatsapp', {'contact':'unknown friend','message':'Hi'})
    assert router.pending is None
    assert 'Say yes' in await router.handle('whatsapp', {'contact':'+919876543210','message':'Hi'})
    assert 'Cancelled' in await router.confirm('no', True)
    assert router.pending is None

def test_no_arbitrary_shell_or_invalid_arguments():
    with pytest.raises(ValueError): validate('launch_app', {'name':'notepad','shell':'rm'})
    with pytest.raises(ValueError): validate('power', {'action':'format'})
    with pytest.raises(ValueError): validate('whatsapp', {'contact':'a'})

@pytest.mark.asyncio
async def test_each_safe_handler(monkeypatch):
    voice = VoiceSession(Socket()); router = voice.router
    monkeypatch.setattr(actions.webbrowser, 'open', lambda url: True)
    async def job(*args): return 'Launched.'
    monkeypatch.setattr(actions, 'desktop_job', job)
    monkeypatch.setattr(actions.music, 'control', lambda *args: 'Music controlled.')
    assert 'Opened' in await router.handle('google_search', {'query':'test'})
    assert 'Opened' in await router.handle('youtube', {})
    assert 'Launched' in await router.handle('youtube', {'query':'test','play':True})
    assert 'Launched' in await router.handle('launch_app', {'name':'notepad'})
    for command in ['play','pause','resume','stop','next']:
        assert 'controlled' in await router.handle('music', {'command':command})
    await router.handle('language', {'language':'hi'})
    assert voice.language == 'hi'
    assert 'It is' in await router.handle('current_time', {})
    assert 'speak' in await router.handle('voice_expression', {})
    assert 'camera' in await router.handle('face_expression', {})
    assert 'not connected' in await router.handle('iot', {'device':'light','action':'on'})

import asyncio
import io
import wave
from unittest.mock import AsyncMock

import httpx
import numpy as np
import pytest

from backend import config
from backend.speech import SpeechRecognizer, filter_transcript, normalize_audio


def pcm():
    return (np.sin(np.arange(16000) * .1) * 1000).astype('<i2').tobytes()


def test_normalization_and_filters():
    audio = normalize_audio(pcm())
    assert np.max(np.abs(audio)) <= config.STT_TARGET_PEAK
    assert np.max(np.abs(audio)) > .2
    for text in ('', 'a', 'Thank you!', 'Thanks for watching.', 'hello hello hello',
                 'open youtube open youtube open youtube'):
        assert filter_transcript(text) == ''
    assert filter_transcript('open youtub') == 'open youtube'
    assert filter_transcript('search youtube for cooking videos') == 'search youtube for cooking videos'
    assert filter_transcript('हाँ') == 'हाँ'
    assert filter_transcript('no') == 'no'


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [RuntimeError('rate limit'), asyncio.TimeoutError()])
async def test_fallback(monkeypatch, error, caplog):
    monkeypatch.setattr(config, 'STT_GROQ_KEY', 'test')
    recognizer = SpeechRecognizer()
    recognizer.groq = AsyncMock(side_effect=error)
    calls = []
    recognizer.transcribe = lambda audio: (calls.append(audio) or ('open youtub', 'en'))
    with caplog.at_level('INFO'):
        assert await recognizer.recognize(pcm(), 12) == ('open youtube', 'en')
    assert len(calls) == 1
    assert 'raw_transcript=' in caplog.text and 'latency_ms=' in caplog.text
    assert 'turn=12 provider=faster-whisper' in caplog.text


@pytest.mark.asyncio
async def test_groq_payload(monkeypatch):
    monkeypatch.setattr(config, 'STT_GROQ_KEY', 'test')
    real_client = httpx.AsyncClient
    def handler(request):
        body = request.content
        assert b'whisper-large-v3-turbo' in body
        assert config.STT_PROMPT.encode() in body
        assert b'name="language"' not in body
        assert b'name="temperature"\r\n\r\n0.0' in body
        start = body.index(b'RIFF')
        with wave.open(io.BytesIO(body[start:]), 'rb') as audio:
            assert audio.getframerate() == 16000
            assert audio.getnchannels() == 1
        return httpx.Response(200, json={'text': 'YouTube kholo', 'language': 'hindi'})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    assert await SpeechRecognizer().recognize(pcm()) == ('youtube kholo', 'hi')


@pytest.mark.asyncio
async def test_ignore_short_audio(monkeypatch):
    recognizer = SpeechRecognizer()
    recognizer.groq = AsyncMock()
    assert await recognizer.recognize(b'\0' * 1000) == ('', 'auto')
    recognizer.groq.assert_not_called()

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from . import config, llm
from .speech import recognizer
from .session import VoiceSession

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']

@asynccontextmanager
async def lifespan(app):
    async def warmup():
        try:
            await asyncio.to_thread(recognizer.load)
        except Exception as exc:
            logging.warning('STT warmup failed: %s. Text input remains available.', type(exc).__name__)
    task = asyncio.create_task(warmup()) if os.getenv('STT_PRELOAD', 'true').lower() == 'true' else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

app = FastAPI(title='Kravox 3.0', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'testserver'])
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET'])

@app.get('/health')
async def health():
    return {'status': 'ok', 'active_provider': llm.active_provider,
            'tts_provider': config.TTS_PROVIDER,
            'stt_model': config.STT_MODEL,
            'tts_voice': config.SARVAM_SPEAKER if config.TTS_PROVIDER == 'sarvam' else config.VOICES,
            'configured_providers': [p[0] for p in config.PROVIDERS if p[3]],
            'provider_errors': llm.provider_errors, 'stt': recognizer.status,
            'wake_available': bool(os.getenv('WAKE_MODEL') and os.path.isfile(os.getenv('WAKE_MODEL')))}

@app.websocket('/ws/voice')
async def voice(ws: WebSocket):
    if ws.headers.get('origin') not in ORIGINS:
        await ws.close(code=1008)
        return
    await ws.accept()
    session = VoiceSession(ws)
    await session.send('hello', **await health())
    try:
        while True:
            packet = await ws.receive()
            if packet['type'] == 'websocket.disconnect':
                break
            try:
                if packet.get('bytes') is not None:
                    await session.receive_audio(packet['bytes'])
                else:
                    import json
                    if len(packet.get('text', '')) > 600_000:
                        raise ValueError('Message too large')
                    data = json.loads(packet.get('text', '{}'))
                    if not isinstance(data, dict):
                        raise ValueError('Expected an object')
                    await session.message(data)
            except (ValueError, TypeError, KeyError):
                await session.send('error', message='Invalid voice message. Please retry.')
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await session.close()

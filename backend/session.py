"""One cancellable voice session per WebSocket."""
import asyncio
import base64
import contextlib
import logging
import time
from . import config, llm
from .speech import recognizer, tts_stream, split_sentences

log = logging.getLogger(__name__)

class VoiceSession:
    def __init__(self, ws):
        self.ws = ws
        self.history = []
        self.turn = 0
        self.task = None
        self.partial_task = None
        self.audio = bytearray()
        self.recording = False
        self.last_partial = 0
        self.language = 'auto'
        self.stt_language = 'auto'
        self.expression = 'neutral'
        self.mode = 'ptt'
        self.sentences = {}
        self.assistant = None
        self.send_lock = asyncio.Lock()
        from .actions import ActionRouter
        self.router = ActionRouter(self)
        self.spoken_input = False
        self.wake_task = None
        self.vision_task = None
        self.emotion_task = None
        from .wake import WakeDetector
        self.wake_detector = WakeDetector()
        self.wake_buffer = bytearray()
        self.voice_estimate = 'Please speak a sentence first, then ask for voice expression estimation.'

    async def send(self, kind, **data):
        async with self.send_lock:
            await self.ws.send_json({'type': kind, 'turn': self.turn, **data})

    async def cancel(self):
        for task in (self.task, self.partial_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self.task = self.partial_task = None

    def spoken_text(self):
        parts = []
        for sentence in self.sentences.values():
            if sentence.get('played'):
                parts.append(sentence['text'])
                continue
            words = []
            for boundary in sentence['boundaries']:
                if boundary['offset'] + boundary['duration'] <= sentence.get('seconds', 0):
                    words.append(boundary['text'])
            parts.append(' '.join(words))
            break
        return ' '.join(p for p in parts if p).strip()

    def commit_spoken(self):
        if self.assistant is not None:
            self.assistant['content'] = self.spoken_text()

    async def interrupt(self):
        await self.cancel()
        self.commit_spoken()
        self.audio.clear()
        self.recording = False
        self.turn += 1
        await self.send('state', state='LISTENING')
        await self.send('history', messages=self.visible_history())

    def visible_history(self):
        return [dict(role=m['role'], content=m.get('content', '')) for m in self.history
                if m['role'] in ('user','assistant') and m.get('content')]

    async def start(self, text=None, pcm=None):
        await self.cancel()
        self.commit_spoken()
        self.turn += 1
        self.sentences = {}
        self.assistant = None
        self.task = asyncio.create_task(self.run_turn(text, pcm))

    async def run_turn(self, text, pcm):
        start = time.perf_counter()
        timing = {'stt_ms': 0, 'llm_first_token_ms': None, 'tts_first_audio_ms': None}
        try:
            await self.send('state', state='THINKING')
            language = self.language
            self.spoken_input = bool(pcm)
            if pcm:
                stt_start = time.perf_counter()
                result = await recognizer.recognize(pcm, self.turn)
                text, detected = result
                language = detected if language == 'auto' else language
                timing['stt_ms'] = round((time.perf_counter() - stt_start) * 1000)
                # Emotion estimation never blocks the first audio path. A completed
                # estimate adjusts subsequent sentences/turns; cancelled jobs cannot update it.
                if self.emotion_task and not self.emotion_task.done(): self.emotion_task.cancel()
                self.emotion_task = asyncio.create_task(self.estimate_voice(pcm))
            if not text or not text.strip():
                await self.send('state', state='LISTENING')
                return
            await self.send('transcript', text=text, final=True)
            self.history.append({'role': 'user', 'content': text})
            # Only complete user-turn groups are retained: no orphaned tool results.
            user_indices = [i for i, m in enumerate(self.history) if m['role'] == 'user']
            if len(user_indices) > 12:
                self.history = self.history[user_indices[-12]:]
            self.assistant = {'role': 'assistant', 'content': ''}
            queue = asyncio.Queue(maxsize=8)

            async def consume():
                index = 0
                while (sentence := await queue.get()) is not None:
                    entry = {'text': sentence, 'boundaries': [], 'seconds': 0, 'played': False}
                    self.sentences[index] = entry
                    await self.send('audio_start', sentence=index, text=sentence)
                    tts_start = time.perf_counter()
                    async for event in tts_stream(sentence, self.language if self.language != 'auto' else language, self.expression):
                        if event['type'] == 'audio':
                            if timing['tts_first_audio_ms'] is None:
                                timing['tts_first_audio_ms'] = round((time.perf_counter() - tts_start) * 1000)
                                timing['first_audio_ms'] = round((time.perf_counter() - start) * 1000)
                            await self.send('audio', sentence=index, data=base64.b64encode(event['data']).decode())
                        else:
                            entry['boundaries'].append(event)
                            await self.send('boundary', sentence=index, **{k:v for k,v in event.items() if k != 'type'})
                    await self.send('audio_end', sentence=index)
                    index += 1

            async def produce():
                buffer = ''
                llm_start = time.perf_counter()
                async for event in self.response_events(text, language):
                    if event['type'] == 'token':
                        if timing['llm_first_token_ms'] is None:
                            timing['llm_first_token_ms'] = round((time.perf_counter() - llm_start) * 1000)
                        await self.send('token', text=event['text'])
                        buffer += event['text']
                        sentences, buffer = split_sentences(buffer)
                        for sentence in sentences:
                            await queue.put(sentence)
                    elif event['type'] == 'provider_fallback':
                        await self.send(**{'kind': event['type'], 'provider': event['provider'], 'reason': event['reason']})
                sentences, _ = split_sentences(buffer, True)
                for sentence in sentences:
                    await queue.put(sentence)
                await queue.put(None)

            # TaskGroup cancels the sibling on failure or parent interruption.
            async with asyncio.TaskGroup() as group:
                group.create_task(consume())
                group.create_task(produce())
            self.history.append(self.assistant)
            await self.send('generation_done')
        except asyncio.CancelledError:
            if self.assistant is not None and not any(m is self.assistant for m in self.history):
                self.history.append(self.assistant)
            raise
        except Exception as exc:
            self.commit_spoken()
            if self.assistant is not None and not any(m is self.assistant for m in self.history):
                self.history.append(self.assistant)
            if isinstance(exc, ExceptionGroup):
                exc = exc.exceptions[0]
            await self.send('error', message=str(exc) if isinstance(exc, RuntimeError) else
                            f'Voice service unavailable ({type(exc).__name__}). Check backend connectivity and model setup.')
            await self.send('generation_done')
        finally:
            log.info('turn=%s timing=%s', self.turn, timing)
            await self.send('timing', **timing)

    async def response_events(self, text, language):
        from .actions import TOOLS
        confirmed = await self.router.confirm(text, self.spoken_input)
        if confirmed is not None:
            yield {'type': 'token', 'text': confirmed}
            return
        messages = [{'role': 'system', 'content': config.SYSTEM_PROMPT +
                     f'\nLanguage preference: {language}. Reply tone hint: {self.expression}.'}]
        messages += [m for m in self.history if m.get('content') or m.get('tool_calls')]
        used = set()
        for _ in range(3):
            calls = []
            content = ''
            async for event in llm.chat_stream(messages, tools=TOOLS):
                if event['type'] == 'tools':
                    calls += event['calls']
                else:
                    if event['type'] == 'token': content += event['text']
                    yield event
            if not calls: return
            import json
            tool_message = {'role':'assistant','content':content or None,'tool_calls':calls}
            messages.append(tool_message)
            self.history.append({**tool_message, 'content': None})
            completed = set()
            try:
                for call in calls:
                    function = call['function']
                    signature = (function['name'], function['arguments'])
                    if signature in used:
                        result = 'This action was already attempted this turn. Do not repeat it.'
                    elif self.router.pending:
                        result = 'An action is awaiting spoken confirmation. Do not request additional actions.'
                    else:
                        used.add(signature)
                        result = await self.router.handle(function['name'], json.loads(function['arguments']))
                    message = {'role':'tool','tool_call_id':call['id'],'content':result}
                    messages.append(message)
                    self.history.append(message)
                    completed.add(call['id'])
            finally:
                # Preserve valid tool-call history even if interruption cancels a handler.
                for call in calls:
                    if call['id'] not in completed:
                        self.history.append({'role':'tool','tool_call_id':call['id'],
                            'content':'Interrupted. An in-flight action may already have been submitted. Check its state before retrying.'})
            if self.router.pending:
                # Speak the exact server-owned confirmation; the model cannot omit it.
                yield {'type':'token','text':self.router.pending['prompt']}
                return
            messages[0]['content'] = config.SYSTEM_PROMPT + f'\nLanguage preference: {self.language}. Reply tone hint: {self.expression}.'
        yield {'type':'token','text':'I reached the action limit for this turn. Please ask me to continue.'}

    async def receive_audio(self, data):
        if not self.recording:
            if self.mode == 'wake' and len(data) <= 65536 and len(data) % 2 == 0:
                if len(self.wake_buffer) < 32000:
                    self.wake_buffer.extend(data)
                if not self.wake_task or self.wake_task.done():
                    pcm = bytes(self.wake_buffer); self.wake_buffer.clear()
                    self.wake_task = asyncio.create_task(self.detect_wake(pcm))
            return
        if len(data) > 65536 or len(data) % 2 or len(self.audio) + len(data) > 16000 * 2 * 30:
            self.audio.clear()
            self.recording = False
            await self.send('error', message='Audio limit reached. Please use sentences under 30 seconds.')
            return
        self.audio.extend(data)

    async def message(self, data):
        kind = data.get('type')
        if kind == 'interrupt':
            await self.interrupt()
        elif kind == 'text':
            text = str(data.get('text', '')).strip()
            if 0 < len(text) <= 4000:
                await self.start(text=text)
        elif kind == 'audio_start':
            await self.cancel()
            self.audio.clear()
            self.recording = True
            await self.send('state', state='LISTENING')
        elif kind == 'audio_end':
            if self.recording:
                pcm = bytes(self.audio)
                self.audio.clear()
                self.recording = False
                if len(pcm) >= config.STT_SAMPLE_RATE * 2 * config.STT_MIN_MS / 1000:
                    await self.start(pcm=pcm)
        elif kind == 'audio_abort':
            self.audio.clear()
            self.recording = False
        elif kind in ('played', 'playback') and data.get('turn') == self.turn:
            entry = self.sentences.get(data.get('sentence'))
            if entry:
                if kind == 'played':
                    entry['played'] = True
                else:
                    entry['seconds'] = max(0, min(float(data.get('seconds', 0)), 600))
                self.commit_spoken()
        elif kind == 'playback_done' and data.get('turn') == self.turn:
            self.commit_spoken()
            await self.send('history', messages=self.visible_history())
            await self.send('state', state='LISTENING')
        elif kind == 'stt_language' and data.get('language') in ('auto', 'en', 'hi'):
            self.stt_language = 'auto'
        elif kind == 'mode' and data.get('mode') in ('ptt', 'always', 'wake'):
            self.mode = data['mode']
            self.wake_buffer.clear()
        elif kind == 'vision':
            if not self.vision_task or self.vision_task.done():
                self.vision_task = asyncio.create_task(self.estimate_face(str(data.get('image', ''))))
        elif kind == 'vision_cancel':
            await self.send('action', name='face_expression', result='Camera permission was not granted.')
        elif kind == 'clear':
            for task in (self.vision_task, self.emotion_task):
                if task and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError): await task
            await self.interrupt()
            self.history.clear()
            self.router.pending = None
            self.assistant = None
            self.sentences.clear()
            await self.send('history', messages=[])

    async def estimate_voice(self, pcm):
        try:
            from .emotion import voice_expression
            self.expression, self.voice_estimate = await asyncio.to_thread(voice_expression, pcm)
        except asyncio.CancelledError: raise
        except Exception:
            self.voice_estimate = 'Voice expression estimation is unavailable. Check librosa installation.'

    async def estimate_face(self, image):
        try:
            from .emotion import face_expression
            self.expression, result = await asyncio.to_thread(face_expression, image)
            await self.send('action', name='face_expression', result=result)
            await self.start(text='Explain this uncertain expression estimation briefly: ' + result)
        except asyncio.CancelledError: raise
        except Exception as exc:
            await self.send('error', message=str(exc) if isinstance(exc, RuntimeError) else 'Could not estimate a face expression. Face the camera in good light and try again.')

    async def detect_wake(self, pcm):
        try:
            if await asyncio.to_thread(self.wake_detector.predict, pcm):
                self.wake_buffer.clear()
                await self.send('wake')
        except asyncio.CancelledError: raise
        except Exception as exc:
            self.mode = 'ptt'
            await self.send('error', message=str(exc) if isinstance(exc, RuntimeError) else 'Wake model could not load. Check the model and openWakeWord setup.')

    async def close(self):
        await self.cancel()
        for task in (self.wake_task, self.vision_task, self.emotion_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError): await task

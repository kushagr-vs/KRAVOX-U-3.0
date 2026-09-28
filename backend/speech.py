"""CPU STT and sentence-at-a-time streaming speech, without microphone ownership."""
import asyncio
import re
import threading
import unicodedata
from . import config

def clean_text(text):
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(?m)^\s*(?:[-*#>]+|\d+[.)])\s*', '', text)
    text = re.sub(r'[*_`~#|<>]', '', text)
    return ' '.join(''.join(c for c in text if unicodedata.category(c)[0] != 'S').split())

def split_sentences(buffer, final=False):
    sentences = []
    while match := re.search(r'[.!?।](?:\s|$)', buffer):
        end = match.end()
        text = clean_text(buffer[:end])
        if text:
            sentences.append(text)
        buffer = buffer[end:]
    # Bound long punctuation-free speech to keep latency and TTS memory bounded.
    while len(buffer) > 180 and ' ' in buffer[:180]:
        end = buffer.rfind(' ', 0, 180)
        sentences.append(clean_text(buffer[:end]))
        buffer = buffer[end + 1:]
    if final and clean_text(buffer):
        sentences.append(clean_text(buffer))
        buffer = ''
    return sentences, buffer

def reply_tone(text, expression='neutral'):
    if expression in ('sad', 'fear', 'angry', 'calm'):
        return 'calm'
    if re.search(r'\b(sorry|sad|unfortunately)\b|दुख|अफ़सोस', text, re.I):
        return 'sad'
    if expression in ('excited', 'happy') or '!' in text or re.search(r'\b(great|congratulations|wonderful)\b|बधाई', text, re.I):
        return 'excited'
    return 'neutral'

class SpeechRecognizer:
    def __init__(self):
        self.model = None
        self.lock = threading.Lock()
        self.status = 'not_loaded'

    def load(self):
        with self.lock:
            return self._load()

    def _load(self):
        if self.model is None:
            self.status = 'loading'
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel(config.STT_MODEL, device='cpu', compute_type='int8',
                                          download_root=str(config.ROOT / 'models'))
                self.status = 'ready'
            except Exception:
                self.status = 'unavailable'
                raise
        return self.model

    def transcribe(self, pcm, partial=False, language='auto'):
        """Local fallback, with one automatic language detection per utterance."""
        if partial:
            return None
        audio = normalize_audio(pcm)
        with self.lock:
            segments, info = self._load().transcribe(audio,
                beam_size=config.STT_BEAM_SIZE, language=None,
                task='transcribe', temperature=config.STT_TEMPERATURE,
                initial_prompt=config.STT_PROMPT, vad_filter=True,
                vad_parameters={'min_silence_duration_ms': config.STT_SILENCE_MS,
                                'speech_pad_ms': config.STT_PAD_MS},
                condition_on_previous_text=False)
            return ''.join(s.text for s in segments).strip(), info.language

    async def recognize(self, pcm, turn=None):
        import logging
        import time
        log = logging.getLogger(__name__)
        start = time.perf_counter()
        raw, language, provider = '', 'auto', 'ignored'
        try:
            if len(pcm) < config.STT_SAMPLE_RATE * 2 * config.STT_MIN_MS / 1000:
                return '', language
            if config.STT_GROQ_KEY:
                try:
                    provider = 'groq'
                    raw, language = await asyncio.wait_for(self.groq(pcm), config.STT_TIMEOUT)
                except Exception as exc:
                    log.warning('STT Groq fallback turn=%s reason=%s', turn, type(exc).__name__)
                    provider = 'faster-whisper'
                    raw, language = await asyncio.to_thread(self.transcribe, pcm)
            else:
                provider = 'faster-whisper'
                raw, language = await asyncio.to_thread(self.transcribe, pcm)
            return filter_transcript(raw), language
        finally:
            log.info('STT turn=%s provider=%s latency_ms=%s raw_transcript=%r',
                     turn, provider, round((time.perf_counter() - start) * 1000), raw)

    async def groq(self, pcm):
        import io
        import wave
        import httpx
        audio = normalize_audio(pcm)
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(config.STT_SAMPLE_RATE)
            output.writeframes((audio * 32767).astype('<i2').tobytes())
        async with httpx.AsyncClient(timeout=config.STT_TIMEOUT) as client:
            response = await client.post('https://api.groq.com/openai/v1/audio/transcriptions',
                headers={'Authorization': 'Bearer ' + config.STT_GROQ_KEY},
                files={'file': ('utterance.wav', wav.getvalue(), 'audio/wav')},
                data={'model': config.STT_GROQ_MODEL, 'temperature': str(config.STT_TEMPERATURE),
                      'prompt': config.STT_PROMPT, 'response_format': 'verbose_json'})
            response.raise_for_status()
            result = response.json()
            if not isinstance(result.get('text'), str):
                raise ValueError('Missing transcription')
            language = result.get('language', 'auto')
            return result['text'], {'english': 'en', 'hindi': 'hi'}.get(language.lower(), language)


def normalize_audio(pcm):
    import numpy as np
    audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
    if audio.size:
        audio -= audio.mean()
        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            audio *= min(config.STT_TARGET_PEAK / peak, config.STT_MAX_GAIN)
    return audio


def filter_transcript(raw):
    from rapidfuzz import fuzz, process
    text = ' '.join(raw.split())
    normalized = ''.join(c for c in text.casefold() if unicodedata.category(c)[0] not in ('P', 'S')).strip()
    words = normalized.split()
    if len(normalized) < config.STT_MIN_CHARS or normalized in config.STT_HALLUCINATIONS:
        return ''
    # Reject repeated words or phrases, but preserve ordinary short commands.
    for size in range(1, len(words) // config.STT_REPEAT_COUNT + 1):
        if len(words) % size == 0 and words == words[:size] * (len(words) // size):
            return ''
    match = process.extractOne(normalized, config.STT_COMMANDS, scorer=fuzz.ratio,
                               score_cutoff=config.STT_FUZZY_THRESHOLD)
    return match[0] if match else text

recognizer = SpeechRecognizer()

async def tts_stream(text, language='en', expression='neutral'):
    if config.TTS_PROVIDER == 'sarvam':
        stream = sarvam_stream(text, language, expression)
    elif config.TTS_PROVIDER == 'edge':
        stream = edge_stream(text, language, expression)
    else:
        raise RuntimeError('TTS_PROVIDER must be sarvam or edge in backend/.env.')
    try:
        async for event in stream:
            yield event
    finally:
        await stream.aclose()

async def sarvam_stream(text, language='en', expression='neutral'):
    """Bulbul v3 binary MP3 streaming; cancellation closes the HTTP connection.

    This endpoint has no word timings. Completed-sentence acknowledgements are
    retained; no fabricated word boundaries are emitted for interrupted speech.
    """
    import httpx
    text = clean_text(text)
    if not text:
        return
    if not config.SARVAM_API_KEY:
        raise RuntimeError('Add SARVAM_API_KEY to backend/.env, or set TTS_PROVIDER=edge for free Edge speech.')
    language = 'hi-IN' if language == 'hi' or re.search(r'[\u0900-\u097f]', text) else 'en-IN'
    payload = {
        'text': text, 'language_code': language, 'speaker': config.SARVAM_SPEAKER,
        'model': config.SARVAM_MODEL, 'speech_sample_rate': 24000,
        'output_audio_codec': 'mp3',
        **config.SARVAM_MODULATION[reply_tone(text, expression)],
    }
    received = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=8)) as client:
            async with client.stream('POST', 'https://api.sarvam.ai/text-to-speech/stream',
                    headers={'api-subscription-key': config.SARVAM_API_KEY}, json=payload) as response:
                if not response.is_success:
                    raise RuntimeError(f'Sarvam TTS returned HTTP {response.status_code}. Check your key and credit balance, or set TTS_PROVIDER=edge.')
                async for chunk in response.aiter_bytes():
                    if chunk:
                        received = True
                        yield {'type': 'audio', 'data': chunk}
        if not received:
            raise RuntimeError('Sarvam returned no audio. Please retry or select Edge TTS.')
    except httpx.HTTPError as exc:
        raise RuntimeError('Sarvam speech connection failed. Please retry or set TTS_PROVIDER=edge.') from exc

async def edge_stream(text, language='en', expression='neutral'):
    import edge_tts
    text = clean_text(text)
    if not text:
        return
    language = 'hi' if re.search(r'[\u0900-\u097f]', text) else language
    voice = config.VOICES.get(language, config.VOICES['en'])
    stream = edge_tts.Communicate(text, voice, boundary='WordBoundary',
                                 **config.MODULATION[reply_tone(text, expression)]).stream()
    try:
        while True:
            try:
                event = await asyncio.wait_for(anext(stream), 15)
            except StopAsyncIteration:
                break
            if event['type'] == 'audio':
                yield {'type': 'audio', 'data': event['data']}
            elif event['type'] == 'WordBoundary':
                yield {'type': 'boundary', 'text': event['text'],
                       'offset': event['offset'] / 10_000_000, 'duration': event['duration'] / 10_000_000}
    finally:
        await stream.aclose()

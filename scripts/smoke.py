"""Run from the project root: python -m scripts.smoke [llm|speech]."""
import asyncio
import sys
import time

async def main():
    if sys.argv[-1] == 'llm':
        from backend.llm import chat_stream
        count = 0
        async for event in chat_stream([{'role': 'user', 'content': 'Say hello in one short sentence.'}]):
            if event['type'] == 'token':
                count += 1
        print(f'LLM smoke passed: {count} streamed text chunks.')
    else:
        from backend.speech import tts_stream, recognizer
        import av
        import io
        import numpy as np
        start = time.perf_counter()
        audio = bytearray()
        async for event in tts_stream('Hello, this is a voice test.'):
            if event['type'] == 'audio':
                if not audio:
                    print(f'TTS first bytes: {(time.perf_counter()-start)*1000:.0f} ms')
                audio.extend(event['data'])
        with av.open(io.BytesIO(audio)) as container:
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            frames = [f.to_ndarray().tobytes() for frame in container.decode(audio=0) for f in resampler.resample(frame)]
            frames += [f.to_ndarray().tobytes() for f in resampler.resample(None)]
        text, language = await asyncio.to_thread(recognizer.transcribe, b''.join(frames))
        assert text and language == 'en', (text, language)
        print(f'STT/TTS round trip passed; language={language}, MP3 bytes={len(audio)}.')

if __name__ == '__main__':
    asyncio.run(main())

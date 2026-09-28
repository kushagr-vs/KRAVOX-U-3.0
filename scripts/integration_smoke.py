"""Non-destructive live WebSocket smoke: text, Hindi, Hinglish, and a clock tool."""
import asyncio
import json
import time
import websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:8000/ws/voice', origin='http://localhost:5173') as ws:
        hello = json.loads(await ws.recv())
        assert hello['type'] == 'hello'
        for prompt in ['Say hello in one short English sentence.', 'नमस्ते, एक छोटे वाक्य में जवाब दो।',
                       'Aaj thoda busy hoon, ek short Hinglish reply do.', 'What time is it? Use the current_time tool.']:
            start = time.perf_counter(); counts = {}; first = None; turn = None
            await ws.send(json.dumps({'type':'text','text':prompt}))
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), 40))
                kind = event['type']; counts[kind] = counts.get(kind, 0) + 1
                turn = event['turn']
                if kind == 'error': raise RuntimeError(event['message'])
                if kind == 'audio' and first is None: first = round((time.perf_counter()-start)*1000)
                if kind == 'audio_end':
                    # Transport test only: simulate acknowledgements, not an acoustic test.
                    await ws.send(json.dumps({'type':'played','turn':turn,'sentence':event['sentence']}))
                if kind == 'generation_done': break
            assert counts.get('token') and counts.get('audio'), counts
            await ws.send(json.dumps({'type':'playback_done','turn':turn}))
            print(f'Turn passed: tokens={counts.get("token")}, audio_chunks={counts.get("audio")}, first_audio_ms={first}, tool_results={counts.get("action",0)}')

if __name__ == '__main__': asyncio.run(main())

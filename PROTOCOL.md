# Local voice protocol

Connect to `ws://localhost:8000/ws/voice` from the Vite app. Only the exact local frontend origins are accepted. A single connection owns its history, pending confirmation, input buffer, and current generation. A reconnect starts a fresh session; the UI retains the previous visible transcript but labels the reset.

Input audio is mono little-endian PCM16, 16 kHz. Send `audio_start`, binary frames, then `audio_end`. The server limits an utterance to 30 seconds and frames to 64 KiB. Periodic partial transcription uses a snapshot, never overlapping inference jobs. `text` with a `text` field starts a typed turn. `interrupt` cancels generation and returns to LISTENING. `mode` sets `ptt`, `always`, or `wake`. `playback` reports `turn`, `sentence`, and `seconds` measured on the actual audio element. `played` acknowledges a completed sentence. `playback_done` indicates the browser queue drained. `vision` carries one explicitly requested camera JPEG. `clear` clears conversation and pending actions.

Output JSON includes `state`, `transcript` (`final` boolean), `token`, `audio_start`, `audio` (base64 MP3 bytes), `boundary` (word text, offset and duration in seconds), `audio_end`, `generation_done`, `history`, `action`, `provider_fallback`, `error`, and `timing`. Audio and text events include a monotonically increasing `turn` and audio has a `sentence` number. After interruption the client rejects the previous turn even if bytes are already in transit. It must stop the audio element and clear buffered audio locally before waiting for the server.

Each sentence has a separate MediaSource MP3 stream. Incoming chunks are appended and played before synthesis finishes. A Blob fallback buffers a sentence on browsers without MP3 MediaSource support; this is visibly reported and has higher latency. Word-boundary metadata plus playback position retain only completed words on interruption. Completed sentences are exact; at the current word boundary this is deliberately conservative. No unsaid tail enters conversational memory. Actions already submitted to the operating system cannot be undone by stopping speech.

Timing reports are milliseconds: STT duration, LLM request to first token, TTS request to first audio bytes, and turn start to first audio bytes. The UI separately measures utterance end to browser playback, and speech-start callback to local queue stop. These measurements do not include the acoustic detector's recognition delay; use an external recording for the 300 ms acceptance test.

Sarvam mode: MP3 audio events use the same protocol, but no boundary events are emitted. Interrupted history retains completed sentences only; the current partial sentence is omitted conservatively.

Input stt_language sets language to auto, en or hi for recognition, independently of reply language.

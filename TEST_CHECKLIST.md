# Acceptance checklist

## Automated / live service verification

- [x] Provider fallback, missing keys, interrupted streams and tool fragment assembly: automated tests.
- [x] Sentence segmentation, Hindi punctuation, markdown cleanup and tone selection: automated tests.
- [x] FastAPI health, allowed WebSocket origin, rejection of foreign origins, input audio limits: automated tests.
- [x] Interrupt cancels simultaneous LLM/TTS tasks inside a 300 ms test deadline; history drops unspoken words and ignores stale acknowledgements.
- [x] Power/WhatsApp validation, fresh spoken confirmation, expiry, cancellation and one-time execution: mocked desktop tests; no real messages or power operations performed.
- [x] Voice expression estimation runs on synthetic audio with librosa and returns uncertain acoustic wording.
- [x] DeepFace dependency import and rejection of a synthetic blank image. Actual-face inference remains a hardware/model acceptance test.
- [x] Browser microphone and Silero VAD initialization; local ONNX module serving corrected for Vite development mode.
- [x] React production build and immediate playback-queue stop unit tests.
- [x] Live Groq streaming using the existing backend key and an available model.
- [x] Live Edge TTS → local Whisper English round trip. Initial first TTS bytes: approximately 2107 ms.
- [x] Browser greeting, real MP3 playback lifecycle, and structured clock action.
- [x] Live WebSocket English, Hindi and Hinglish text-to-speech turns plus clock tool: first audio bytes at 1597, 2554, 1698 and 2302 ms respectively. This excludes STT and does not measure acoustic output.

## Hardware / account acceptance — complete on your computer

These are not claimed as passed by mocked tests.

1. **English:** say “Tell me one fun fact about the moon.” Check transcript accuracy, a natural 1–3 sentence answer, and English voice.
2. **Hindi:** say “आज मैं क्या नया सीख सकता हूँ?” Check Devanagari transcript and Hindi speech. Repeat after “Speak English,” then “हिंदी में बात करो.”
3. **Hinglish:** say “Aaj kaafi busy hoon, ek quick break idea do.” Check mixed-language understanding and a short casual reply.
4. **Barge-in:** use Always listening and ask for a three-sentence reply. Start speaking during sentence one. Record microphone and speaker externally, and measure acoustic onset to silence; target ≤300 ms. Repeat ten times with headphones and speakers. Inspect history: the unsaid tail must be absent. The UI's local_stop_ms excludes VAD detection delay.
5. **First speech latency:** run ten warmed turns in each language. Record `heard_ms` in the side panel. Report median/p95 and CPU/model; target ≈1500 ms. Do not call this passed based on server first-byte timing alone.
6. **Provider fallback:** remove/blank `GROQ_API_KEY`, configure NVIDIA or run Ollama, restart the backend, and ask a question. `/health.active_provider` must change. Repeat with both cloud keys blank and a pulled Ollama model. Simulate HTTP 429 and a stalled stream via tests; do not exhaust a free quota deliberately.
7. **Search:** ask for a Google query, YouTube homepage, YouTube search, and a specific music video. Confirm the default browser and encoded search are correct.
8. **Local music:** put two supported audio files in Music. Verify play, pause, resume, next, named selection, and stop. Check a missing song gives a truthful result.
9. **Wikipedia:** ask for a topic, then a nonsense topic; verify a relevant summary or a truthful no-result/error response.
10. **Apps:** configure the exact VS Code path, then ask to open VS Code and Notepad. An unlisted app must not execute arbitrary input.
11. **Power:** request restart and say no; the system must stay running. Test yes only when you are ready to restart/shut down/log out. Verify expired and typed confirmations cannot execute.
12. **WhatsApp:** log in to WhatsApp Web. Use your own test recipient, provide a message, and cancel once. Then request again and give spoken confirmation. Check the exact recipient/message in the chat and delivery status. The app must not claim verified delivery.
13. **Expression estimation:** speak quietly and energetically; observations must remain uncertain. Click camera, accept/deny permission in separate tests, test a visible face and a blank frame. Camera tracks must stop after capture. No diagnosis claims.
14. **Wake:** after supplying a custom model, verify “Kravox” wakes the app, unrelated speech does not, and muting ends listening. Without a model, the mode must show setup needed.
15. **IoT:** “Turn on the light” and “Is there smoke?” must report not connected; no fabricated sensor readings.
16. **Reliability:** deny mic permission, stop/restart the backend, switch modes mid-sentence, rapidly interrupt twice, clear history while speaking, and test an unavailable TTS connection. No stale audio should resume, and reconnect must explain the fresh session.
17. **Style:** try ten everyday questions. Replies should be direct, casual, short, without spoken markdown, emojis or long lists.

Final repeated live run: English/Hindi/Hinglish first audio bytes were 1950/1314/1457 ms; the clock-tool turn took 15899 ms. All completed, but free-provider/tool latency varies substantially. These are transport timings, not end-to-end microphone measurements.

Sarvam update: 17 backend tests pass. Verify Shubh live after checking your free-credit balance; confirm English/Hindi streaming, pace presets, interrupt and completed-sentence history. Live Sarvam synthesis has not been claimed as tested.

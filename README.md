# KRAVOX 3.0 — local voice companion

A FastAPI + React upgrade of the supplied Python desktop assistant. Talk in English, Hindi, or Hinglish, interrupt a spoken reply, and use desktop tools through a local browser UI.

## Start on Windows

Use **Python 3.12** and **Node.js 22.12+**. The old `venv/` points to a missing Python installation; use the new `.venv/`. Commands below run in PowerShell from this project's root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Webcam expression estimation (large TensorFlow dependency):
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-vision.txt
# Only on a fresh checkout without an existing backend/.env:
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
notepad backend\.env
```

Your existing root `.env` was moved to `backend/.env` without printing its contents. Preserve it. The runtime reads this exact file, regardless of the working directory. Restart the backend after changing keys or model names. No key is served to React. The existing Sarvam key is used when TTS_PROVIDER=sarvam.

Terminal 1, from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173** in Chrome or Edge. Click the microphone button and allow microphone access. In Push to talk, hold the **Hold to talk** button (or Space/Enter while it has focus), speak, then release. Always listening ends a turn after about 700 ms of silence. Muting stops microphone tracks. Text works without microphone access.

`python kravox.py` also starts the backend; `python kravox_gui.py` opens the web UI after both servers are running. `kravox_core.py` exports the asynchronous session and streaming client. Original desktop sources are preserved in `legacy-desktop.zip`; they are not imported by the web app.

## Free LLM setup

1. **Groq:** sign in to the [Groq console](https://console.groq.com/keys), create an API key, and put it in `GROQ_API_KEY` in `backend/.env`. Use the free plan; do not enable a paid plan. See the [official quickstart](https://console.groq.com/docs/quickstart) and [free-plan rate limits](https://console.groq.com/docs/rate-limits). The live-tested default here is `openai/gpt-oss-120b`. Model availability changes; `python -m scripts.provider_diagnostic` prints available IDs without printing credentials.
2. **NVIDIA:** join the free Developer Program at [build.nvidia.com](https://build.nvidia.com), open a model, select **Get API Key**, and put the key in `NVIDIA_API_KEY`. Choose the model ID shown in its API example as `NVIDIA_MODEL`. The client uses `https://integrate.api.nvidia.com/v1`. NVIDIA describes this access as free **prototyping**, subject to limits, not unlimited production hosting: [official FAQ](https://docs.api.nvidia.com/nim/docs/product), [API quickstart](https://docs.api.nvidia.com/nim/re/docs/api-quickstart). Do not sign up for a paid deployment or enter a credit card for this app.
3. **Ollama:** install [Ollama](https://ollama.com), then run:

```powershell
ollama pull qwen3:4b
ollama serve
```

If Ollama is already running, skip `ollama serve`. Set `OLLAMA_MODEL` to a locally installed model with tool-call support. Ollama is the free local fallback if provider access or free quotas are unavailable. It needs sufficient RAM and CPU/GPU resources.

`chat_stream(messages)` tries Groq → NVIDIA → Ollama. Missing keys are skipped. HTTP errors, rate limits, and eight seconds without a stream delta cause fallback. After a partial response the next provider is asked to continue the text; natural-language continuation can vary. Completed tool calls are executed outside the retry loop and are deduplicated per turn. `/health` reports configured providers, the last provider that actually emitted output, errors, and STT readiness; configured does not mean reachable.

## Speech and latency

Whisper `small` uses CPU int8, automatic language detection, and VAD filtering. First startup downloads model files into `backend/models/`; warmup runs in the background so text stays usable. Use `STT_MODEL=small` for potentially better recognition at higher CPU cost. Multilingual Whisper supports mixed speech, but Hinglish transcription and accent accuracy still need testing with your voice.

Browser Silero VAD, its worklet, and ONNX runtime files are copied locally by `npm ci`; no CDN is needed at runtime. `getUserMedia` enables echo cancellation, noise suppression, and automatic gain control. Headphones usually improve interruption detection when speakers cause echo.

LLM tokens feed a bounded sentence queue. The selected TTS provider starts per sentence while the LLM continues generating. MP3 bytes stream over the same WebSocket and play through MediaSource. English uses `en-US-GuyNeural`, Hindi uses `hi-IN-MadhurNeural`; edit `backend/config.py` for voices and calm/excited/sad/neutral rate/pitch presets. Reply text is stripped of markdown and symbols before synthesis. [Edge TTS](https://github.com/rany2/edge-tts) uses an online service without an API key; it is free but is not an offline TTS engine or a guaranteed service.

**1.5 seconds is a target, not an achieved guarantee.** The initial live TTS-only test returned its first bytes in about 2.1 seconds. CPU recognition, silence detection, free-tier queues and network delay add time. Turn timings are logged and shown in the side panel. Measure warm English/Hindi/Hinglish turns before claiming the target is met. Browsers without MP3 MediaSource support buffer a whole sentence and show a notice.

On speech-start the client pauses and clears the playback queue immediately, reports the playback position, and sends `interrupt`. The server cancels the LLM and TTS task group. Turn IDs reject stale audio. Word timing from Edge TTS plus browser playback acknowledgements retains only completed words in interrupted assistant history. This is conservative at the current word boundary. The 300 ms automated cancellation checks measure software paths; real acoustic speech-start-to-silence needs the checklist's microphone test.

## Commands and configuration

All commands use LLM function calling with server-side argument validation. The action log shows actual handler results.

| Ask for | Behavior / setup |
| --- | --- |
| Google search | Opens an encoded search in your default browser. |
| YouTube search / open / play | Opens the homepage or search; play uses pywhatkit's first matching result. Browser autoplay may require a click. |
| Play / pause / resume / stop / next music | Controls MP3/WAV/OGG/FLAC files in `MUSIC_DIR` or your Music folder through pygame. Does not control unrelated external players. |
| Wikipedia | Fetches a short extract from Wikipedia's API and lets the LLM summarize it. |
| Open VS Code / an app | Uses the allowlist in `backend/apps.json`. Correct the VS Code executable path for your installation; add aliases as argument arrays. No arbitrary shell tool is exposed. |
| Shutdown / restart / logout | Windows handler asks for a spoken yes/no. Confirmation expires in 60 seconds and can be consumed once. Typed yes asks you to use the mic. |
| Send WhatsApp | Tell it a contact/number and exact message. For aliases, copy `contacts.example.json` to `contacts.json` and edit it. A full international number is required. After spoken confirmation, pywhatkit uses your logged-in WhatsApp Web browser. Check the chat for delivery; desktop automation cannot verify delivery. |
| Speak Hindi / English | Changes per-session reply language; `auto` restores matching. |
| Voice expression | Estimates pitch and energy from your latest utterance using librosa. Runs off the first-audio path; a completed estimate affects later synthesis. This cannot determine your feelings. |
| Face expression | Requests one webcam frame via browser permission, runs DeepFace locally, then releases the camera. Detection must find a face. Model weights download on first use. Results are uncertain expression estimates, never diagnoses. |
| Lights / smoke / ESP32 | Returns an explicit not-connected result. `backend/mqtt.py` is the requested TODO interface; no device action is claimed. |

`PyWhatKit_DB.txt` in the supplied project is a message audit log, not a contacts database or a Python library. No `PyWhatKit_DB.zip` was present in the project or attachments. The log was left intact; no private phone numbers were imported as contacts. A pywhatkit send may append to its own log, so do not publish that file.

Once a confirmed action reaches the operating system or WhatsApp, stopping speech cannot undo it. Cancellation terminates an in-flight desktop worker where possible and records an uncertain outcome; check before repeating the action.

## Optional “Kravox” wake word

openWakeWord does not ship a pretrained “Kravox” model. Supply a custom trained ONNX model using the [openWakeWord training guide](https://github.com/dscripka/openWakeWord#training-new-models). Training is a separate step; a placeholder model is not included.

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-wake.txt
.\.venv\Scripts\python.exe -c "import openwakeword.utils; openwakeword.utils.download_models()"
```

Set `WAKE_MODEL` in `backend/.env` to the model's absolute path and restart. The mode is enabled only when that file exists. Say “Kravox”, pause briefly, then speak. Audio used for wake detection stays on the local backend. A wake model load error switches the backend to Push to talk and shows the error. Always listening and Push to talk work without a wake model.

## Tests and diagnostics

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m scripts.smoke llm
.\.venv\Scripts\python.exe -m scripts.smoke speech
# With the backend running:
.\.venv\Scripts\python.exe -m scripts.integration_smoke
cd frontend
npm test
npm run build
```

See `TEST_CHECKLIST.md` for hardware and live action acceptance tests, `PROTOCOL.md` for message formats, `FILE_MANIFEST.md` for all changes and the folder tree, and `SOURCE_DELIVERY.md` for complete source files in separate fenced blocks. `.env`, personal contact data, model binaries and dependencies are deliberately excluded from the source listing.

## Privacy and troubleshooting

Both servers bind to loopback. Only `localhost:5173` and `127.0.0.1:5173` origins can use the voice socket. Use this as a single-user local app; do not expose port 8000 to a network. Conversation state is held in memory per connection. Reconnection starts a fresh backend session; the UI warns you. Audio and camera frames are not saved by the app. Cloud LLM providers receive conversation text and tool results; the selected TTS provider (Sarvam or Edge) receives reply text for speech. Ollama keeps LLM processing local, but Edge still needs internet.

If the mic fails, allow the permission for localhost, close apps holding exclusive mic access, or use the text input. If audio is blocked, click Enable audio and retry. If all providers fail, check `/health`, the configured model IDs and keys, or start Ollama. For sluggish first turns, wait for `/health` to show `stt: ready`; model loading and the first librosa call can take time. Keep the old `venv/` separate from `.venv/`.



## Sarvam Shubh voice (selected)

The selected TTS provider is now Sarvam **Bulbul v3**, speaker **shubh**, for English, Hindi and code-mixed replies. It uses the binary MP3 streaming endpoint and the existing interruptible playback queue. Configure only in `backend/.env`:

```dotenv
TTS_PROVIDER=sarvam
SARVAM_API_KEY=your_key
SARVAM_MODEL=bulbul:v3
SARVAM_SPEAKER=shubh
```

The migrated key is reused without exposing it to React. Restart the backend after changing these settings. `/health` exposes the selected TTS provider and voice, never the key. Set `TTS_PROVIDER=edge` to return to Guy/Madhur.

Bulbul v3 supports pace and temperature, not pitch/loudness. Tone presets adjust pace; temperature controls generation variability, not a guaranteed emotion. No pitch parameter is sent. Sarvam is credit-based, with signup credits rather than unlimited free usage; no payment or top-up was enabled by this change. Check your dashboard balance before use. See [pricing](https://www.sarvam.ai/api-pricing) and [streaming API](https://docs.sarvam.ai/api-reference/text-to-speech/convert-stream).

Sarvam's MP3 endpoint has no word timestamps. On interruption, history conservatively retains completed sentences and drops the current partial sentence; Edge retains its finer word-boundary behavior. No estimated timestamps are presented as exact. Connection/key/credit errors appear in the UI; the app does not silently switch voices.

Validation: 17 backend tests pass, including the Shubh request payload, MP3 stream routing, missing-key and credit-error handling. Live Sarvam synthesis was not run because the remaining free-credit balance is unknown.


## Indian-accent recognition update

The default local recognizer is now multilingual Whisper `small` with beam size 5 for final transcripts, deterministic decoding, and a short Kravox/app-name vocabulary hint. Partial captions keep fast decoding and are provisional. Audio stays local. This is a general multilingual model, not an Indian-accent fine-tune; improved accuracy on your voice still needs a real microphone comparison.

Use the new **Speech language** selector: **English · Indian accent** pins English decoding for short Indian-English commands; **Hindi / Hinglish** pins Hindi; **Auto** detects the language. This setting is separate from the reply-language preference. Longer 700 ms endpoint silence and 400 ms of pre-speech audio help preserve pauses and initial syllables. Backend VAD also retains additional speech padding. These accuracy-oriented settings can add latency on CPU. Shubh speech output remains selected.

18 backend tests and the frontend build passed. The small model was downloaded and loaded successfully. Refresh the frontend after the update.

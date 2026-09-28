# File manifest and final folder tree

## Changed / moved

- `kravox.py`: local FastAPI launcher; original source archived.
- `kravox_core.py`: compatibility exports for VoiceSession and chat_stream.
- `kravox_gui.py`: opens the local React interface.
- `test.py`: runs backend tests instead of the desktop SAPI speech test.
- `.env` moved to `backend/.env`; secret contents preserved and excluded from delivery listings.

No original source or personal data was deleted. `legacy-desktop.zip` contains the four original Python files. `data.txt`, `PyWhatKit_DB.txt`, `kravox_voice.mp3`, and the old `venv/` remain unchanged. The ZIP is an archival copy, not the active application.

## New files / tree

```text
KRAVOX 2.0/
├── .gitignore
├── README.md
├── PROTOCOL.md
├── TEST_CHECKLIST.md
├── FILE_MANIFEST.md
├── SOURCE_DELIVERY.md       generated complete source listing
├── requirements.txt
├── legacy-desktop.zip
├── kravox.py               changed
├── kravox_core.py          changed
├── kravox_gui.py           changed
├── test.py                 changed
├── backend/
│   ├── .env                moved, private
│   ├── .env.example
│   ├── __init__.py
│   ├── app.py
│   ├── config.py
│   ├── llm.py
│   ├── speech.py
│   ├── session.py
│   ├── actions.py
│   ├── desktop_worker.py
│   ├── apps.json
│   ├── contacts.example.json
│   ├── emotion.py
│   ├── wake.py
│   ├── mqtt.py
│   ├── requirements-vision.txt
│   └── requirements-wake.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   ├── scripts/copy-vad.mjs
│   ├── tests/audio.test.mjs
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── audio.js
│       └── style.css
├── scripts/
│   ├── smoke.py
│   ├── integration_smoke.py
│   ├── provider_diagnostic.py
│   └── export_sources.py
└── tests/
    ├── test_llm.py
    ├── test_speech.py
    ├── test_session.py
    ├── test_actions.py
    └── test_emotion.py
```

Generated runtime directories: `.venv/`, `.pytest_cache/`, Python `__pycache__/`, `backend/models/` (Whisper and DeepFace cache), `frontend/node_modules/`, `frontend/public/vad/` (local model/worklet/runtime assets), `frontend/dist/` (production build). These contain dependency/build files rather than handwritten source and are ignored. The existing root `__pycache__/` may contain legacy bytecode.

## Verification and remaining setup

14 backend tests and 2 frontend tests passed; production build passed. Live Groq, Edge TTS, Whisper English round trip, multilingual text-to-speech WebSocket turns, and the clock tool passed. Browser VAD initialization passed after correcting local ONNX module serving. DeepFace import and blank-frame rejection passed.

Real acoustic barge-in latency and end-to-end 1.5-second speech latency remain unverified. Custom Kravox wake-word training, configured contacts/app paths, real WhatsApp delivery and power actions require the user's setup and acceptance tests. Face expression on an actual webcam face requires first-use model weights and the user's camera. NVIDIA and Ollama live fallback cannot be verified without those providers configured; fallback behavior is covered by deterministic tests. MQTT remains the explicitly requested stub.

Additional generated deliverable: kravox-preview.png (final browser screenshot).

Voice update: backend/config.py now selects Guy (English) and Madhur (Hindi), with a neutral -5% rate and -10Hz pitch and adjusted tone presets. README.md and SOURCE_DELIVERY.md updated.

Sarvam update: changed backend/config.py, backend/speech.py, backend/app.py, backend/.env.example, private backend/.env, README.md, PROTOCOL.md, FILE_MANIFEST.md, TEST_CHECKLIST.md and regenerated SOURCE_DELIVERY.md. Added tests/test_sarvam.py. Shubh/Bulbul v3 is selected; Edge remains configurable. No files deleted.

Indian-accent STT update: changed backend/config.py, backend/speech.py, backend/session.py, backend/app.py, backend/.env.example, private backend/.env, frontend/src/App.jsx, frontend/src/style.css, tests/test_speech.py, README.md, PROTOCOL.md, FILE_MANIFEST.md; regenerated SOURCE_DELIVERY.md and frontend/dist. Downloaded the multilingual small model into backend/models.

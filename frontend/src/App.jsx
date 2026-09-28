import React, { useEffect, useRef, useState } from 'react';
import { SpeechPlayer, pcm16 } from './audio';
import { STT } from './stt-config';

const API = 'http://127.0.0.1:8000';
function Icon({ name, size = 20 }) {
  const paths = { mic: <><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></>,
    stop: <rect x="6" y="6" width="12" height="12" rx="3"/>, send: <><path d="m5 12 7-7 7 7M12 5v15"/></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></>,
    camera: <><path d="M3 7h4l2-3h6l2 3h4v13H3z"/><circle cx="12" cy="13" r="4"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/> };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export default function App() {
  const [connected, setConnected] = useState(false), [state, setState] = useState('IDLE');
  const [mode, setMode] = useState('ptt'), [mic, setMic] = useState(false), [held, setHeld] = useState(false);
  const [caption, setCaption] = useState(''), [user, setUser] = useState(''), [input, setInput] = useState('');
  const [history, setHistory] = useState([]), [actions, setActions] = useState([]), [panel, setPanel] = useState(false);
  const [error, setError] = useState(''), [provider, setProvider] = useState('LOCAL SESSION'), [wake, setWake] = useState(false);
  const [timing, setTiming] = useState(null), [level, setLevel] = useState(0), [starting, setStarting] = useState(false);
  const runtime = useRef({ mode: 'ptt', chunks: [], speechSamples: 0, captureSamples: 0, mic: false, capture: false, held: false, ring: [], turn: 0, floor: 0, wakeArmed: false });
  const ws = useRef(null), vad = useRef(null), player = useRef(null), mounted = useRef(true);
  const send = data => { if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(data instanceof ArrayBuffer ? data : JSON.stringify(data)); };
  if (!player.current) player.current = new SpeechPlayer(send, setState, setError, setLevel);
  function interrupt() {
    const start = performance.now(); player.current.stop();
    runtime.current.floor = runtime.current.turn + 1;
    send({ type: 'interrupt' }); setState('LISTENING');
    setTiming(t => ({ ...t, local_stop_ms: Math.round(performance.now() - start) }));
  }
  function beginCapture() {
    const r = runtime.current;
    if (!r.mic || r.capture || ws.current?.readyState !== WebSocket.OPEN) return;
    interrupt(); r.capture = true; send({ type: 'audio_start' });
    r.chunks = r.ring; r.ring = []; r.speechSamples = 0;
    r.captureSamples = r.chunks.reduce((n, frame) => n + frame.length, 0);
  }
  function endCapture() {
    const r = runtime.current;
    if (!r.capture) return;
    r.capture = false; r.wakeArmed = false; r.ring = []; r.endedAt = performance.now();
    if (r.speechSamples >= STT.sampleRate * STT.minSpeechMs / 1000) {
      // Transfer only after the utterance ends; chunk sizes respect WS limits.
      for (const frame of r.chunks) send(pcm16(frame));
      send({ type: 'audio_end' }); setState('THINKING');
    } else { send({ type: 'audio_abort' }); setState('LISTENING'); }
    r.chunks = [];
  }
  useEffect(() => {
    mounted.current = true; let timer, attempts = 0, disposed = false;
    function connect() {
      const socket = new WebSocket('ws://127.0.0.1:8000/ws/voice'); ws.current = socket;
      socket.onopen = () => {
        if (disposed) return socket.close();
        setConnected(true); attempts = 0; runtime.current.turn = 0; runtime.current.floor = 0;
        setError(previous => previous.startsWith('Backend disconnected.') ? 'Reconnected. A fresh conversation is ready.' : previous);
        send({ type: 'mode', mode: runtime.current.mode });
      };
      socket.onmessage = ({ data }) => {
        let e; try { e = JSON.parse(data); } catch { return; }
        if (e.turn < runtime.current.floor) return;
        if (e.turn > runtime.current.turn) { runtime.current.turn = e.turn; setCaption(''); }
        if (e.type === 'hello') {
          setWake(e.wake_available); setState('IDLE');
          setProvider(e.active_provider || 'READY');
          if (!e.configured_providers.some(p => p !== 'ollama')) setError('No cloud key configured. Start Ollama, or add a free key to backend/.env.');
        }
        if (e.type === 'state') setState(e.state);
        if (e.type === 'transcript') { setUser(e.text); if (e.final) setHistory(h => [...h, { role: 'user', content: e.text }]); }
        if (e.type === 'token') setCaption(c => c + e.text);
        if (e.type.startsWith('audio') || e.type === 'generation_done') player.current.handle(e);
        if (e.type === 'history') setHistory(e.messages);
        if (e.type === 'action') setActions(a => [...a.slice(-49), e]);
        if (e.type === 'error') { setError(e.message); player.current.stop(); setState('LISTENING'); }
        if (e.type === 'provider_fallback') setError(`${e.provider}: ${e.reason}. Trying the next provider…`);
        if (e.type === 'timing') setTiming(t => ({ ...t, ...e }));
        if (e.type === 'wake') { runtime.current.wakeArmed = true; beginCapture(); }
        if (e.type === 'camera_request') captureCamera();
      };
      socket.onclose = () => {
        if (disposed) return;
        setConnected(false); player.current.stop(); runtime.current.capture = false;
        setState('IDLE'); setError('Backend disconnected. Reconnecting; a new connection starts a fresh conversation.');
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 10000));
      };
      socket.onerror = () => socket.close();
    }
    connect();
    const healthTimer = setInterval(() => fetch(`${API}/health`).then(r => r.json()).then(h => {
      if (!disposed) { setProvider(h.active_provider || 'READY'); setWake(h.wake_available); }
    }).catch(() => {}), 5000);
    return () => { disposed = true; mounted.current = false; clearTimeout(timer); clearInterval(healthTimer); ws.current?.close(); vad.current?.destroy().catch(() => {}); player.current.stop(); if (player.current.context?.state !== 'closed') player.current.context?.close().catch(() => {}); };
  }, []);
  player.current.onFirstPlay = () => {
    const r = runtime.current;
    if (r.endedAt) { setTiming(t => ({ ...t, heard_ms: Math.round(performance.now() - r.endedAt) })); r.endedAt = null; }
  };
  async function enableMic() {
    if (starting) return;
    setStarting(true); setError('');
    try {
      await player.current.unlock();
      const { MicVAD } = await import('@ricky0123/vad-web');
      if (!vad.current) vad.current = await MicVAD.new({
        model: 'v5', startOnLoad: false, baseAssetPath: '/vad/', onnxWASMBasePath: '/vad/',
        ortConfig: ort => { ort.env.wasm.numThreads = 1; ort.env.logLevel = 'error'; },
        positiveSpeechThreshold: STT.positiveThreshold, negativeSpeechThreshold: STT.negativeThreshold,
        redemptionMs: STT.silenceMs, preSpeechPadMs: STT.prePaddingMs, minSpeechMs: STT.minSpeechMs,
        getStream: () => navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1, sampleRate: STT.sampleRate } }),
        onFrameProcessed: (probabilities, frame) => {
          const r = runtime.current; if (!r.mic) return;
          if (!player.current.current) setLevel(Math.sqrt(frame.reduce((n, v) => n + v*v, 0) / frame.length) * 10);
          if (r.capture) {
            const remaining = STT.sampleRate * STT.maxUtteranceMs / 1000 - r.captureSamples;
            const captured = frame.slice(0, Math.max(0, remaining));
            r.chunks.push(captured); r.captureSamples += captured.length;
            if (probabilities.isSpeech >= STT.negativeThreshold) r.speechSamples += frame.length;
            if (r.captureSamples >= STT.sampleRate * STT.maxUtteranceMs / 1000) endCapture();
          }
          else {
            r.ring.push(frame.slice()); if (r.ring.length > Math.ceil(STT.sampleRate * STT.prePaddingMs / 1000 / STT.frameSamples)) r.ring.shift();
            if (r.mode === 'wake') send(pcm16(frame));
          }
        },
        onSpeechStart: () => {
          const r = runtime.current;
          if (r.mic && (r.mode === 'always' || r.held || r.wakeArmed || player.current.current)) beginCapture();
        },
        onSpeechEnd: () => endCapture(),
        onVADMisfire: () => {
          if (runtime.current.mode === 'ptt' && runtime.current.held) return;
          runtime.current.capture = false; runtime.current.chunks = []; send({ type: 'audio_abort' }); setState('LISTENING');
        },
      });
      if (!mounted.current) { await vad.current.destroy(); return; }
      runtime.current.mic = true; await vad.current.start(); setMic(true); setState('LISTENING');
    } catch (err) { runtime.current.mic = false; setMic(false); setError(`Microphone unavailable (${err.name}: ${err.message}). Check microphone permission and local VAD assets, or use text below.`); }
    finally { setStarting(false); }
  }
  async function toggleMic() {
    if (!mic) return enableMic();
    runtime.current.mic = false; runtime.current.capture = false; runtime.current.ring = [];
    runtime.current.held = false; setHeld(false); send({ type: 'audio_abort' });
    await vad.current?.pause(); setMic(false); setLevel(0); setState('IDLE');
  }
  function selectMode(value) {
    endCapture(); runtime.current.mode = value; runtime.current.held = false; runtime.current.wakeArmed = false;
    setHeld(false); setMode(value); send({ type: 'mode', mode: value });
  }
  async function submit(event) {
    event.preventDefault(); if (!input.trim() || !connected) return;
    setError('');
    await player.current.unlock().catch(() => setError('Audio is unavailable; you can still read the captions.'));
    interrupt(); runtime.current.endedAt = performance.now();
    send({ type: 'text', text: input.trim() }); setInput('');
  }
  async function captureCamera() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
      const video = document.createElement('video'); video.srcObject = stream; video.muted = true;
      await video.play();
      if (!video.videoWidth) await new Promise(resolve => { video.onloadeddata = resolve; });
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      canvas.getContext('2d').drawImage(video, 0, 0, 640, 480);
      send({ type: 'vision', image: canvas.toDataURL('image/jpeg', 0.75).split(',')[1] });
    } catch { setError('Camera permission is required for expression estimation.'); send({ type: 'vision_cancel' }); }
    finally { stream?.getTracks().forEach(t => t.stop()); }
  }
  const label = !connected ? 'Waiting for connection' : !mic && state === 'LISTENING' ? 'Ready when you are' : ({ IDLE: 'Ready when you are', LISTENING: 'I’m listening', THINKING: 'A moment of thought', SPEAKING: 'Let’s talk' }[state]);
  function holdStart(e) { if (!mic || mode !== 'ptt') return; e?.currentTarget?.setPointerCapture?.(e.pointerId); runtime.current.held = true; setHeld(true); beginCapture(); }
  function holdEnd() { runtime.current.held = false; setHeld(false); endCapture(); }
  return <div className="app">
    <header><a className="brand" href="/" aria-label="Kravox home"><span className="brand-mark">K</span> KRAVOX <span className="version">3.0</span></a><div className="header-right"><span className={`connection ${connected ? 'online' : ''}`}><i/>{connected ? 'Local connection' : 'Reconnecting'}</span><button className="icon-button" aria-label="Toggle conversation panel" onClick={() => setPanel(!panel)}><Icon name="panel"/></button></div></header>
    <main>
      <div className="eyebrow"><span/> YOUR SPACE TO THINK OUT LOUD</div>
      <h1>Voice, naturally.</h1><p className="subtitle">A little curiosity. A real conversation. Just you and Kravox.</p>
      <div className={`orb-stage ${state.toLowerCase()}`} style={{ '--level': Math.min(level, 1.5) }} aria-hidden="true"><div className="orbit one"/><div className="orbit two"/><div className="orb"><div className="orb-flow"/><div className="orb-shine"/></div><div className="orb-shadow"/></div>
      <div className="status"><span className={`status-dot ${state.toLowerCase()}`}/>{label}</div>
      <section className="captions" aria-label="Live captions" aria-live="polite"><p className="user-caption">{user || 'English, हिंदी, or a little of both.'}</p><p className="reply-caption">{caption || (state === 'IDLE' ? 'Where should we begin?' : '\u00a0')}</p></section>
      {error && <div className="notice" role="status"><span>{error}</span><button aria-label="Dismiss notice" onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
      <div className="recognition-language">Speech language · Auto (English / Hindi / Hinglish)</div><div className="controls"><button className={`mic-button ${mic ? 'active' : ''}`} disabled={!connected || starting} onClick={toggleMic} aria-label={mic ? 'Mute microphone' : 'Enable microphone'}><Icon name="mic" size={23}/></button><select aria-label="Listening mode" value={mode} onChange={e => selectMode(e.target.value)}><option value="ptt">Push to talk</option><option value="always">Always listening</option><option value="wake" disabled={!wake}>Wake word · Kravox{!wake ? ' (setup needed)' : ''}</option></select><button className="icon-button" onClick={interrupt} disabled={!connected} aria-label="Stop speaking"><Icon name="stop"/></button><button className="icon-button" disabled={!connected} onClick={captureCamera} aria-label="Estimate facial expression"><Icon name="camera"/></button></div>
      {mode === 'ptt' ? <button className={`hold-button ${held ? 'held' : ''}`} disabled={!mic || !connected} onPointerDown={holdStart} onPointerUp={holdEnd} onPointerCancel={holdEnd} onKeyDown={e => { if ([' ', 'Enter'].includes(e.key) && !e.repeat) { e.preventDefault(); holdStart(); } }} onKeyUp={e => { if ([' ', 'Enter'].includes(e.key)) { e.preventDefault(); holdEnd(); } }} onBlur={() => { if (runtime.current.held) holdEnd(); }}>{starting ? 'Preparing microphone…' : !mic ? 'Enable your mic to start' : held ? 'Listening… release to send' : 'Hold to talk'}</button> : <p className="mode-hint">{!mic ? 'Enable your mic to start' : mode === 'wake' ? 'Say “Kravox” to start a turn' : 'Speak freely. You can interrupt anytime.'}</p>}
      <form className="composer" onSubmit={submit}><input aria-label="Message Kravox" placeholder="Or type a thought…" maxLength={4000} value={input} onChange={e => setInput(e.target.value)}/><button type="submit" disabled={!input.trim() || !connected} aria-label="Send message"><Icon name="send"/></button></form>
      <div className="below-composer"><span>Built for conversation, in your language.</span><button onClick={() => player.current.unlock().catch(() => setError('Audio is unavailable.'))}>Enable audio</button></div>
    </main>
    <footer><span><i/> {provider.toUpperCase()}</span><span>LOCAL FIRST <b>·</b> FREE TO EXPLORE</span><span>KRAVOX / 03</span></footer>
    {panel && <><button className="scrim" aria-label="Close conversation panel" onClick={() => setPanel(false)}/><aside><div className="panel-title"><h2>Your conversation</h2><button className="icon-button" onClick={() => setPanel(false)} aria-label="Close panel"><Icon name="close"/></button></div><button className="clear" onClick={() => { player.current.stop(); send({ type: 'clear' }); setHistory([]); setCaption(''); setUser(''); }}>New conversation</button><div className="history">{history.length ? history.map((m, i) => <article key={i}><small>{m.role === 'user' ? 'YOU' : 'KRAVOX'}</small><p>{m.content}</p></article>) : <p className="empty">Your conversation will appear here.</p>}</div><h3>Actions</h3><div className="action-log">{actions.length ? actions.map((a, i) => <p key={i}><small>{a.name}</small>{a.result}</p>) : <p className="empty">No actions yet.</p>}</div>{timing && <details><summary>Turn timing</summary><pre>{Object.entries(timing).filter(([k]) => k.endsWith('_ms')).map(([k,v]) => `${k}: ${v ?? '—'} ms`).join('\n')}</pre></details>}<p className="privacy">Mic audio goes to Groq for transcription, with local Whisper as fallback. Reply text goes to your selected LLM and Edge TTS. Camera frames stay on this computer.</p></aside></>}
  </div>;
}


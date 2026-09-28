/** Play MP3 bytes as they arrive. Each sentence is its own cancellable stream. */
export class SpeechPlayer {
  constructor(send, state, error, volume) {
    Object.assign(this, { send, state, error, volume });
    this.items = new Map(); this.queue = []; this.current = null; this.done = false;
  }
  async unlock() {
    if (!this.context || this.context.state === 'closed') this.context = new AudioContext();
    await this.context.resume();
  }
  handle(event) {
    const key = `${event.turn}:${event.sentence}`;
    if (event.type === 'audio_start') {
      const item = { ...event, key, chunks: [], ended: false };
      this.items.set(key, item); this.queue.push(item); this.done = false; this.next();
    } else if (event.type === 'audio') {
      const item = this.items.get(key); if (!item) return;
      item.chunks.push(Uint8Array.from(atob(event.data), c => c.charCodeAt(0)));
      if (item === this.current) this.pump();
    } else if (event.type === 'audio_end') {
      const item = this.items.get(key); if (!item) return;
      item.ended = true; if (item === this.current) this.pump();
    } else if (event.type === 'generation_done') {
      this.done = true; this.turn = event.turn; this.next();
    }
  }
  next() {
    if (this.current) return;
    const item = this.queue.shift();
    if (!item) {
      if (this.done) { this.done = false; this.send({ type: 'playback_done', turn: this.turn }); }
      return;
    }
    this.current = item;
    const audio = new Audio(); item.audio = audio;
    audio.onplaying = () => { this.state('SPEAKING'); this.onFirstPlay?.(); };
    audio.onended = () => {
      if (this.current !== item) return;
      this.send({ type: 'played', turn: item.turn, sentence: item.sentence });
      this.release(item); this.current = null; this.next();
    };
    audio.onerror = () => { this.error('Audio playback failed. Try Chrome or Edge and send your message again.'); this.stop(); };
    item.interval = setInterval(() => this.progress(), 80);
    if (this.context) {
      item.source = this.context.createMediaElementSource(audio);
      item.analyser = this.context.createAnalyser(); item.analyser.fftSize = 256;
      item.source.connect(item.analyser); item.analyser.connect(this.context.destination);
      const samples = new Uint8Array(128);
      const meter = () => {
        if (this.current !== item) return;
        item.analyser.getByteFrequencyData(samples);
        this.volume(samples.reduce((a, b) => a + b, 0) / samples.length / 100);
        item.raf = requestAnimationFrame(meter);
      }; meter();
    }
    if (typeof MediaSource !== 'undefined' && MediaSource.isTypeSupported('audio/mpeg')) {
      item.media = new MediaSource(); item.url = URL.createObjectURL(item.media); audio.src = item.url;
      item.media.addEventListener('sourceopen', () => {
        if (this.current !== item) return;
        try {
          item.buffer = item.media.addSourceBuffer('audio/mpeg');
          item.buffer.addEventListener('updateend', () => this.pump()); this.pump();
          audio.play().catch(() => this.error('Playback needs a click. Use Enable audio, then retry.'));
        } catch { this.error('Streaming audio is unavailable in this browser. Try Chrome or Edge.'); this.stop(); }
      }, { once: true });
    } else {
      item.fallback = true;
      this.error('This browser buffers each sentence before playback. Chrome or Edge supports lower-latency streaming.');
      this.pump();
    }
  }
  pump() {
    const item = this.current; if (!item) return;
    if (item.fallback) {
      if (item.ended && !item.url) {
        item.url = URL.createObjectURL(new Blob(item.chunks, { type: 'audio/mpeg' }));
        item.audio.src = item.url; item.chunks = [];
        item.audio.play().catch(() => this.error('Click Enable audio, then retry.'));
      }
      return;
    }
    if (!item.buffer || item.buffer.updating || item.media.readyState !== 'open') return;
    try {
      if (item.chunks.length) item.buffer.appendBuffer(item.chunks.shift());
      else if (item.ended) item.media.endOfStream();
    } catch { this.error('The audio stream could not be decoded. Please retry.'); this.stop(); }
  }
  progress() {
    const item = this.current;
    if (item) this.send({ type: 'playback', turn: item.turn, sentence: item.sentence, seconds: item.audio.currentTime || 0 });
  }
  release(item) {
    clearInterval(item.interval); cancelAnimationFrame(item.raf);
    item.audio?.pause();
    if (item.audio) { item.audio.onended = null; item.audio.onerror = null; item.audio.removeAttribute('src'); item.audio.load(); }
    item.source?.disconnect(); item.analyser?.disconnect();
    if (item.url) URL.revokeObjectURL(item.url);
    this.items.delete(item.key); this.volume(0);
  }
  stop() {
    this.progress();
    if (this.current) this.release(this.current);
    this.current = null; this.queue = []; this.items.clear(); this.done = false;
  }
}

export function pcm16(frame) {
  const out = new Int16Array(frame.length);
  for (let i = 0; i < frame.length; i++) out[i] = Math.max(-1, Math.min(1, frame[i])) * 32767;
  return out.buffer;
}

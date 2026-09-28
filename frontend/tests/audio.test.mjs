import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pcm16, SpeechPlayer } from '../src/audio.js';

test('PCM conversion clamps samples', () => {
  assert.deepEqual([...new Int16Array(pcm16(new Float32Array([-2, 0, 2])))], [-32767, 0, 32767]);
});
test('interrupt synchronously pauses and clears every queued stream', () => {
  let paused = false; const events = [];
  globalThis.cancelAnimationFrame = () => {};
  const player = new SpeechPlayer(e => events.push(e), () => {}, () => {}, () => {});
  player.current = { key:'4:0', turn:4, sentence:0, audio:{ currentTime:.42, pause(){paused=true;}, removeAttribute(){}, load(){} } };
  player.queue = [{ key:'4:1' }]; player.done = true;
  const start = performance.now(); player.stop();
  assert.ok(performance.now()-start < 300);
  assert.ok(paused); assert.equal(player.current, null); assert.deepEqual(player.queue, []);
  assert.equal(events[0].seconds, .42);
  assert.equal(player.done, false);
});

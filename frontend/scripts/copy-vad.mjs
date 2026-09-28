import { mkdir, copyFile, readdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
const require = createRequire(import.meta.url);
const target = new URL('../public/vad/', import.meta.url);
await mkdir(target, { recursive: true });
const vadDist = path.dirname(require.resolve('@ricky0123/vad-web'));
const ortDist = path.dirname(require.resolve('onnxruntime-web'));
for (const dir of [vadDist, ortDist]) {
  for (const name of await readdir(dir)) {
    if (/\.onnx$|\.wasm$|\.mjs$|vad\.worklet\.bundle\.min\.js$/.test(name)) {
      await copyFile(path.join(dir, name), new URL(name, target));
    }
  }
}

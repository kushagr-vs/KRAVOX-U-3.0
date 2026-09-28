import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
// ONNX imports its runtime dynamically. Serve local runtime modules before
// Vite's import transformer, which rejects imports from public/.
const localRuntime = { name: 'local-vad-runtime', configureServer(server) {
  server.middlewares.use(async (req, res, next) => {
    const pathname = (req.url || '').split('?')[0];
    if (!/^\/vad\/ort-[\w.-]+\.mjs$/.test(pathname)) return next();
    try {
      const body = await readFile(path.join(server.config.root, 'public', pathname));
      res.setHeader('Content-Type', 'text/javascript'); res.end(body);
    } catch { next(); }
  });
} };
export default defineConfig({ plugins: [localRuntime, react()], server: { host: '127.0.0.1', port: 5173, strictPort: true } });

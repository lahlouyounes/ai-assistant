import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const rootDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(rootDir, 'app/static'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/chat': 'http://127.0.0.1:8000',
      '/actions': 'http://127.0.0.1:8000',
      '/sessions': 'http://127.0.0.1:8000',
      '/documents': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
});

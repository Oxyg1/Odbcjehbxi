import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const sharedSrc = fileURLToPath(new URL('../../packages/shared/src', import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Пакет отдаётся исходниками, поэтому подключаем его напрямую,
      // минуя пребандлинг: одна копия типов и схемы на монорепо.
      '@plsdonate/shared': `${sharedSrc}/index.ts`,
    },
  },
  optimizeDeps: {
    exclude: ['@plsdonate/shared'],
  },
  server: {
    host: true,
    fs: { allow: [sharedSrc, fileURLToPath(new URL('.', import.meta.url))] },
  },
  build: {
    target: 'es2020',
  },
});

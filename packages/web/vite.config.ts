import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Telegram loads the Mini App over https from a tunnel in development.
    allowedHosts: true,
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    rollupOptions: {
      output: {
        // Framer Motion and TON Connect are large and change rarely; splitting
        // them keeps the app shell cheap to re-download on each deploy.
        manualChunks: {
          motion: ['framer-motion'],
          tonconnect: ['@tonconnect/ui-react'],
        },
      },
    },
  },
});

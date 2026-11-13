/// <reference types="vitest/config" />
import { resolve } from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Development only: the browser stays same-origin and Vite forwards to the API.
// Production routing is the reverse proxy in infra/nginx.conf on the one APP_PORT.
const devBackend = process.env.SFL_DEV_BACKEND ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [tanstackRouter(), react(), tailwindcss()],
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': { target: devBackend, changeOrigin: false },
      '/media': { target: devBackend, changeOrigin: false },
      '/ws': { target: devBackend, ws: true, changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
})

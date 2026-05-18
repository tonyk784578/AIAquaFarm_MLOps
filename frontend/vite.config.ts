/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  // ES2022 enables top-level await (used in main.tsx for the optional mock loader)
  // and matches the modern browser baseline.
  build: {
    target: 'es2022',
  },
  esbuild: {
    target: 'es2022',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,   // proxy WebSocket connections (/api/v1/ws/*)
      },
      '/agents': {
        target: process.env.VITE_AGENT_BASE_URL || 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/agents/, ''),
      },
    },
  },
  // ── Vitest ───────────────────────────────────────────────────────────────
  // Tests live in src/**/*.test.{ts,tsx} and run under jsdom. The setup file
  // registers @testing-library/jest-dom matchers and stubs EventSource.
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['src/test/**', 'src/mocks/**', '**/*.d.ts'],
    },
  },
})

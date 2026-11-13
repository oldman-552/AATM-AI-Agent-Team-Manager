import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In token mode the API token stays in this Node process and is injected into
// proxied requests; it is never exposed to the browser bundle.
const apiToken = process.env.AATM_AUTH_TOKEN

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    allowedHosts: ['localhost', '127.0.0.1', '.e2b.app'],
    proxy: {
      '/api': {
        target: process.env.AATM_API_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
        headers: apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined,
      },
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In token mode the API token stays in this Node process and is injected into
// proxied requests; it is never exposed to the browser bundle.
const apiToken = process.env.AATM_AUTH_TOKEN

export default defineConfig({
  plugins: [react()],
  build: {
    // Split the rarely-changing vendor code from the application code, so a UI
    // edit does not invalidate the React/lucide bundle in the browser cache, and
    // so no single chunk crosses the 500 kB warning threshold.
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('react') || id.includes('scheduler')) return 'react'
          if (id.includes('i18next') || id.includes('@tanstack') || id.includes('lucide')) return 'data'
          // Anything else is small enough to stay in the app chunk; naming it
          // would produce an empty vendor chunk, which Rollup then warns about.
          return undefined
        },
      },
    },
  },
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

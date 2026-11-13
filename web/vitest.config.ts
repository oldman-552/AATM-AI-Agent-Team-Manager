import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    // The resource tests are pure Node; the render test needs a DOM, so it is
    // opted into jsdom per file with a `@vitest-environment` comment.
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})

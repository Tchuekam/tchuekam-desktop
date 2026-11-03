import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    exclude: ['dist/**', 'node_modules/**'],
    // cursorDriftRegression walks every typing-prefix of a 570-char message
    // across seven terminal widths, calling wrap-ansi on each — about 8000
    // calls over growing prefixes, so the work is quadratic in message
    // length by design (that breadth is the point of the pin). It needs
    // ~16s on a 4-core box and blew vitest's 5s default; under CI
    // contention it is slower still. Mirrors the testTimeout bump in
    // apps/desktop/vite.config.ts, which was raised for the same reason.
    testTimeout: 30000,
    hookTimeout: 30000
  }
})

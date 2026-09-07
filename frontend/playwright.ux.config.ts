import { defineConfig, devices } from "@playwright/test";

// Separate ports and fixture mode keep UX checks independent of a live local demo.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", testMatch: /ux\.spec\.ts/, use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } } },
  ],
  webServer: [
    { command: "..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8011", url: "http://127.0.0.1:8011/health", env: { LLM_MODE: "fixture", REG_BRIDGE_DATABASE_PATH: "../results/ux-verification.sqlite3", REG_BRIDGE_CORS_ORIGINS: '["http://127.0.0.1:5174"]' }, timeout: 60_000 },
    { command: "npm run dev -- --host 127.0.0.1 --port 5174 --strictPort", url: "http://127.0.0.1:5174", env: { VITE_API_BASE_URL: "http://127.0.0.1:8011" }, timeout: 60_000 },
  ],
});

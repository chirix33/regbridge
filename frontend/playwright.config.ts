import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-1440",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "chromium-1280",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 720 } },
    },
  ],
  webServer: [
    {
      command:
        "powershell -NoProfile -ExecutionPolicy Bypass -Command \"$env:LLM_MODE='fixture'; Remove-Item Env:LLM_API_KEY -ErrorAction SilentlyContinue; Remove-Item Env:LLM_BASE_URL -ErrorAction SilentlyContinue; Remove-Item Env:LLM_MODEL -ErrorAction SilentlyContinue; Set-Location ..\\backend; ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000\"",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});

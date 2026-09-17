import { defineConfig, devices } from "@playwright/test";
import base from "./playwright.ux.config";
export default defineConfig({ ...base, projects: [
  { name: "review-1440", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  { name: "review-1280", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 720 } } },
  { name: "review-390", testMatch: /(?:ux|review-ui)\.spec\.ts/, use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true } },
] });

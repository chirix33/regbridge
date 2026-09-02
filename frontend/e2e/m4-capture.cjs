const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("@playwright/test");

const repositoryRoot = path.resolve(__dirname, "../..");
const outputDir = path.join(repositoryRoot, "paper", "figures", "m4");
const snapshotPath = path.join(
  repositoryRoot,
  "data",
  "presentation",
  "m4",
  "m4-phase2-20260901T170811002109Z-v1",
  "snapshot.json",
);

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

async function capturePage(page, entry) {
  await page.setViewportSize(entry.viewport);
  await page.goto(entry.route);
  if (entry.fixture_id) {
    await page.getByRole("button", { name: /Parse and analyze/i }).click();
    await page.locator(".analysis-results").waitFor({ state: "visible" });
  } else {
    await page.getByText(/Presentation snapshot derived from frozen Phase 2 run/i).waitFor();
  }
  const screenshotPath = path.join(outputDir, entry.file);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  return { ...entry, image_sha256: sha256File(screenshotPath) };
}

(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const snapshot = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
  const viewport = { width: 1440, height: 900 };
  const entries = [
    {
      id: "case-a-evidence-graph",
      file: "case-a-evidence-graph.png",
      route: "/demo/case-a",
      fixture_id: "case-a-removed-3212",
      viewport,
      purpose: "Case A evidence and graph trace",
    },
    {
      id: "case-c-b2-regbridge-contrast",
      file: "case-c-b2-regbridge-contrast.png",
      route: "/demo/case-c",
      fixture_id: "case-c-stale-applicant",
      viewport,
      purpose: "Case C B2/RegBridge contrast path",
    },
    {
      id: "case-b-metadata-behavior",
      file: "case-b-metadata-behavior.png",
      route: "/demo/case-b",
      fixture_id: "case-b-manufacturer-all-preservation",
      viewport,
      purpose: "Case B lifecycle-sensitive metadata behavior",
    },
    {
      id: "held-out-comparison-dashboard",
      file: "held-out-comparison-dashboard.png",
      route: "/evaluation",
      fixture_id: null,
      viewport,
      purpose: "Held-out comparison dashboard",
    },
  ];

  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL: "http://127.0.0.1:5173" });
  const captured = [];
  for (const entry of entries) {
    captured.push(await capturePage(page, entry));
  }
  await browser.close();

  const manifest = {
    schema_version: "m4.screenshot-manifest.v1",
    snapshot_version: snapshot.snapshot_version,
    snapshot_sha256: snapshot.snapshot_sha256,
    capture_command: ".\\scripts\\m4-capture.ps1",
    captured_at: "2026-09-01T00:00:00Z",
    entries: captured,
  };
  fs.writeFileSync(
    path.join(outputDir, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
})();

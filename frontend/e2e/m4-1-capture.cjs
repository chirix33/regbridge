const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("@playwright/test");

const repositoryRoot = path.resolve(__dirname, "../..");
const outputDir = path.join(repositoryRoot, "paper", "figures", "m4-1");
const archivePath = path.join(
  repositoryRoot,
  "data",
  "demo-dossiers",
  "m4-1",
  "regbridge-m4-1-composite.zip",
);

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

async function screenshot(page, id, file, purpose) {
  const target = path.join(outputDir, file);
  await page.screenshot({ path: target, fullPage: true });
  return {
    id,
    file,
    route: new URL(page.url()).pathname,
    viewport: { width: 1440, height: 900 },
    purpose,
    image_sha256: sha256File(target),
  };
}

(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 900 },
  });
  const entries = [];

  await page.goto("/");
  await page.getByLabel("Dossier ZIP").setInputFiles(archivePath);
  await page.getByLabel(/I confirm this target context/i).check();
  await page.getByRole("button", { name: "Parse and analyze" }).click();
  await page.getByText("HUMAN_REGULATORY_REVIEW").waitFor();
  entries.push(
    await screenshot(
      page,
      "analyzer-profile-and-summary",
      "analyzer-profile-and-summary.png",
      "Authenticity-hardened profile checks and dossier-level three-document summary",
    ),
  );

  await page.getByRole("button", { name: /Synthetic substance properties/i }).click();
  await page.getByRole("heading", { name: "Chronological trace" }).waitFor();
  entries.push(
    await screenshot(
      page,
      "case-a-complete-trace",
      "case-a-complete-trace.png",
      "Uploaded Case A decision, repair, evidence, graph, and trace",
    ),
  );

  await page.getByRole("button", { name: /Synthetic applicant responsibility statement/i }).click();
  await page.getByRole("heading", { name: "Chronological trace" }).waitFor();
  entries.push(
    await screenshot(
      page,
      "case-c-semantic-review",
      "case-c-semantic-review.png",
      "Uploaded Case C regional-metadata versus PDF semantic review trace",
    ),
  );

  await page.getByRole("link", { name: "Baselines" }).click();
  await page.getByRole("button", { name: /Run four systems/i }).click();
  await page.getByRole("heading", { name: /Comparison completed/i }).waitFor();
  entries.push(
    await screenshot(
      page,
      "package-derived-system-comparison",
      "package-derived-system-comparison.png",
      "Label-free package-derived B0, B1, B2, and RegBridge comparison",
    ),
  );

  await browser.close();
  const manifest = {
    schema_version: "m4.1.screenshot-manifest.v1",
    capture_command: ".\\scripts\\m4-1-capture.ps1",
    captured_at: "2026-09-02T00:00:00Z",
    fixture_mode: true,
    archive: "data/demo-dossiers/m4-1/regbridge-m4-1-composite.zip",
    archive_sha256: sha256File(archivePath),
    input_profile_id: "fda-ectd-322-regbridge-demo-profile-v1",
    operational_status: "not_operational",
    expert_validated: false,
    entries,
  };
  fs.writeFileSync(
    path.join(outputDir, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
})();

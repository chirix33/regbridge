import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("M4 guided journey and dashboard are accessible", async ({ page }) => {
  await page.goto("/about");
  await expect(page.getByText("FDA forward compatibility: not_operational")).toBeVisible();

  await page.getByRole("link", { name: /Open shared analyzer/i }).click();
  await expect(page).toHaveURL(/\/demo\/case-a$/);
  await page.getByRole("button", { name: /Parse and analyze/i }).click();
  await expect(page.getByRole("heading", { name: /REUSE WITH NEW CONTEXT/i })).toBeVisible();
  await expect(page.getByRole("table", { name: /Graph edge table/i })).toBeVisible();

  await page.getByRole("link", { name: /^Evaluation$/i }).first().click();
  await expect(page.getByText(/results are displayed, not recomputed/i)).toBeVisible();
  await expect(page.getByText("B1 BM25 retrieval metrics")).toBeVisible();
  await expect(page.getByText(/genuine deterministic experimental output/i)).toBeVisible();

  const results = await new AxeBuilder({ page: page as never }).exclude(".graph-board").analyze();
  expect(results.violations).toEqual([]);
});

test("M4.2 uploads the public-standards ZIP and compares package-derived inputs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Analyze a dossier" })).toBeVisible();
  await expect(page.getByText(/Not validated by a regulatory expert/i)).toBeVisible();
  await page.getByLabel("Dossier ZIP").setInputFiles("../data/demo-dossiers/m4-2/regbridge-m4-2-public-standards.zip");
  await page.getByRole("button", { name: "Continue to options" }).click();
  await expect(page.getByLabel("Analysis model")).toHaveCount(0);
  await expect(page.getByText("Offline demonstration", { exact: true })).toBeVisible();
  await page.getByLabel("How should metadata be handled?").selectOption("preserve-existing-lifecycle");
  await page.getByLabel(/I confirm this target context/i).check();
  await page.getByRole("button", { name: "Parse and analyze" }).click();
  await expect(page.getByRole("heading", { name: "Your dossier results" })).toBeFocused();
  await expect(page.getByRole("button", { name: "Parse and analyze" })).toHaveCount(0);
  await page.getByText("Package checks and document coverage", { exact: true }).click();
  await expect(page.getByText(/fda-cder-ectd-322-public-standards-profile-v1/)).toBeVisible();
  await expect(page.getByText(/ich-ectd-dtd-v3-2 3.2.2 \(passed\)/)).toBeVisible();
  await expect(page.getByText(/fda-us-regional-dtd-v3-3 3.3 \(passed\)/)).toBeVisible();
  await expect(page.getByText(/Index-dtd-version-inferred/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Needs attention" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Context and metadata" }).click();
  const caseA = page.locator(".document-review").filter({ hasText: "Synthetic molecular structure" });
  await expect(caseA.getByText(/Proposed document recommendation: Reuse with a new context/)).toBeVisible();
  await expect(caseA.locator(".document-filename")).toContainText(".pdf");
  await caseA.getByText("View supporting evidence", { exact: true }).click();
  await expect(caseA.getByRole("link", { name: "Official source" }).first()).toBeVisible();
  await caseA.getByText("How RegBridge reached this result", { exact: true }).click();
  await expect(caseA.getByRole("table", { name: "Graph edge table" })).toBeVisible();
  await expect(caseA.getByText("3.2.S.1.2", { exact: true }).first()).toBeVisible();
  await expect(caseA.getByText("3.2.S.1.1", { exact: true })).toHaveCount(0);
  await expect(caseA.getByText("3.2.S.1.3", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/macro-F1|unsafe-FNR|accuracy/i)).toHaveCount(0);

  await page.getByRole("link", { name: "Baselines" }).click();
  await expect(page.getByText(/3 documents are available/i)).toBeVisible();
  await expect(page.getByLabel("How should metadata be handled?")).toHaveValue("preserve-existing-lifecycle");
  await page.getByRole("button", { name: "Run comparison" }).click();
  await expect(page.getByRole("heading", { name: "Your comparison results" })).toBeFocused();
  await expect(page.getByText("B2 · Rules only", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/winner|superiority/i)).toHaveCount(0);

  const results = await new AxeBuilder({ page: page as never }).analyze();
  expect(results.violations).toEqual([]);
});

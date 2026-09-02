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

test("M4.1 uploads the real composite ZIP and compares package-derived inputs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Inspect reuse risk from the package itself/i })).toBeVisible();
  await expect(page.getByText(/expert_validated: false/i)).toBeVisible();
  await expect(page.getByRole("option", { name: /Qwen 3.6 local/i })).toHaveAttribute("disabled", "");
  await page.getByLabel("Dossier ZIP").setInputFiles("../data/demo-dossiers/m4-1/regbridge-m4-1-composite.zip");
  await page.getByLabel(/I confirm this target context/i).check();
  await page.getByRole("button", { name: "Parse and analyze" }).click();
  await expect(page.getByRole("heading", { name: "Controlled v3.2.2 profile checks" })).toBeVisible();
  await expect(page.getByText("REUSE_WITH_NEW_CONTEXT")).toBeVisible();
  await expect(page.getByText("REUSE_AS_LEGACY_REFERENCE")).toBeVisible();
  await expect(page.getByText("HUMAN_REGULATORY_REVIEW")).toBeVisible();
  await expect(page.getByText(/macro-F1|unsafe-FNR|accuracy/i)).toHaveCount(0);

  await page.getByRole("link", { name: "Baselines" }).click();
  await expect(page.getByText(/Reusing 3-document inventory/i)).toBeVisible();
  await page.getByRole("button", { name: /Run four systems/i }).click();
  await expect(page.getByRole("heading", { name: /Comparison completed/i })).toBeVisible();
  await expect(page.getByText("B2 · No LLM").first()).toBeVisible();
  await expect(page.getByText(/winner|superiority/i)).toHaveCount(0);

  const results = await new AxeBuilder({ page: page as never }).analyze();
  expect(results.violations).toEqual([]);
});

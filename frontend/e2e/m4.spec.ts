import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("M4 guided journey and dashboard are accessible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("FDA forward compatibility: not_operational")).toBeVisible();

  await page.getByRole("link", { name: /Open shared analyzer/i }).click();
  await expect(page).toHaveURL(/\/demo\/case-a$/);
  await page.getByRole("button", { name: /Parse and analyze/i }).click();
  await expect(page.getByRole("heading", { name: /REUSE WITH NEW CONTEXT/i })).toBeVisible();
  await expect(page.getByRole("table", { name: /Graph edge table/i })).toBeVisible();

  await page.getByRole("link", { name: /^Evaluation$/i }).click();
  await expect(page.getByText(/results are displayed, not recomputed/i)).toBeVisible();
  await expect(page.getByText("B1 BM25 retrieval metrics")).toBeVisible();
  await expect(page.getByText(/genuine deterministic experimental output/i)).toBeVisible();

  const results = await new AxeBuilder({ page: page as never }).exclude(".graph-board").analyze();
  expect(results.violations).toEqual([]);
});

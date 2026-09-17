/// <reference lib="dom" />
import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import fixture from "../src/test/fixtures/m43-product.json" with { type: "json" };

test("review UI: concrete actions, modal focus, light layouts, and retained routes", async ({ page }, info) => {
  const capture = async (name: string) => {
    const modal = await page.getByRole("dialog").count() > 0;
    if (!modal) await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: !modal });
  };
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Choose your dossier" })).toBeVisible();
  await capture("01-upload");
  await page.getByRole("button", { name: "Try a sample dossier" }).click();
  await expect(page.getByText(/Selected: regbridge/)).toBeVisible();
  await page.getByRole("button", { name: "Continue to options" }).click();
  await page.getByRole("radio", { name: "Preserve existing metadata" }).check();
  const help = page.getByRole("button", { name: "About plan metadata changes" });
  await help.focus();
  await expect(page.getByRole("note")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("note")).toHaveCount(0);
  await expect(page.getByRole("radio", { name: "Preserve existing metadata" })).toBeChecked();
  if (info.project.use.hasTouch) {
    await help.tap();
    await expect(page.getByRole("note")).toBeVisible();
    await page.getByRole("heading", { name: "Choose your review options" }).tap();
    await expect(page.getByRole("note")).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "Preserve existing metadata" })).toBeChecked();
  }
  await expect(page.locator(".flow-boundary")).toHaveCount(0);
  await capture("02-options");
  // Production parser + recorded contract responses exercise the reported abstention mix.
  await page.route("**/api/v1/dossier-analyses", route => route.fulfill({ json: { ...fixture.run, results: [fixture.abstention.results[0], fixture.abstention.results[1], fixture.run.results[2]] } }));
  await page.getByLabel(/I confirm/).check();
  await page.getByRole("button", { name: "Parse and analyze" }).click();
  const queue = page.getByRole("table", { name: "Action overview" });
  await expect(queue.getByRole("button")).toHaveCount(3);
  await expect(queue.getByText("Incomplete inspection", { exact: true })).toHaveCount(2);
  await expect(queue).toContainText('manufacturer="all"');
  await capture("03-actions");
  await page.getByRole("button", { name: "All documents" }).click();
  await expect(page.getByRole("table", { name: "Document inventory" }).getByRole("button")).toHaveCount(3);
  await capture("04-inventory");
  await page.getByRole("button", { name: "Needs attention" }).click();
  const opener = page.getByRole("button", { name: "Document placement" });
  await opener.scrollIntoViewIfNeeded();
  const scrollBefore = await page.evaluate(() => window.scrollY);
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Document placement" });
  await expect(dialog).toBeVisible();
  const close = dialog.getByRole("button", { name: "Close document review" });
  await expect(close).toBeFocused();
  await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => Boolean(document.activeElement?.closest("dialog")))).toBe(true);
  await close.focus();
  await dialog.locator(".dialog-content").evaluate(el => { el.scrollTo({ top: 0, behavior: "instant" }); });
  await capture("05-document");
  await dialog.getByText("View supporting evidence", { exact: true }).click();
  await expect(dialog.getByRole("link", { name: "Official source" }).first()).toBeVisible();
  await dialog.getByText("How this conclusion is supported", { exact: true }).click();
  await dialog.locator(".graph-edge-table").scrollIntoViewIfNeeded();
  await capture("06-long-dialog");
  await expect(close).toBeInViewport();
  expect((await new AxeBuilder({ page: page as never }).analyze()).violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(Math.abs(await page.evaluate(() => window.scrollY) - scrollBefore)).toBeLessThan(3);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("html")).toHaveCSS("scroll-behavior", "auto");
  if (info.project.use.hasTouch) {
    await opener.tap();
    await close.tap();
  } else {
    await opener.click();
    await close.click();
  }
  await expect(dialog).toHaveCount(0);
  await page.goto("/baselines");
  await expect(page.getByRole("radio", { name: "Preserve existing metadata" })).toBeChecked();
  await page.getByRole("button", { name: "Run comparison" }).click();
  await expect(page.getByRole("heading", { name: "Your comparison results" })).toBeVisible();
  await expect(page.getByText("Inspection omitted (B2)", { exact: true })).toHaveCount(3);
  await capture("07-baselines");
  await page.locator(".comparison-table tbody tr").first().screenshot({ path: info.outputPath("07-baseline-card.png") });
  await page.getByRole("button", { name: "B0 · Document agent: explanation and evidence" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("No graph reasoning is supplied by this approach");
  await page.keyboard.press("Escape");
  await page.goto("/about");
  await capture("08-about");
  expect((await new AxeBuilder({ page: page as never }).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await capture("09-about-200-percent");
  expect(await page.evaluate(() => document.body.getBoundingClientRect().width <= innerWidth + 1)).toBe(true);
});

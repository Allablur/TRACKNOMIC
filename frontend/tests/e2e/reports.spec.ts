import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
test("downloads filtered CSV and a PDF through the UI", async ({ page }) => {
  await page.goto("/reports");
  await page.getByLabel("Search artist").fill("Velvet");
  await page.getByRole("button", { name: "Apply filters" }).click();
  for (const format of ["CSV", "PDF"]) {
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: `Download ${format}` }).click(),
    ]);
    expect(await download.failure()).toBeNull();
    expect(download.suggestedFilename()).toBe(
      `trackonomics-catalogue.${format.toLowerCase()}`,
    );
    const file = await download.path();
    expect(file).not.toBeNull();
    const data = await readFile(file!);
    if (format === "CSV") {
      expect(data.toString()).toContain("Velvet Meridian");
      expect(data.toString()).not.toContain("Atlas in Bloom");
    } else expect(data.subarray(0, 4).toString()).toBe("%PDF");
  }
});

import { test, expect } from "@playwright/test";
test("mobile layout remains usable with keyboard navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await expect(
    page
      .locator("article")
      .filter({ hasText: "Tracked artists" })
      .getByText("6", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Artists", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Artist intelligence" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Velvet Meridian", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

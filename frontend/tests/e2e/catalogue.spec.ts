import { test, expect } from "@playwright/test";
test("dashboard renders seeded counts and attributed charts", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(
    page
      .locator("article")
      .filter({ hasText: "Tracked artists" })
      .getByText("6", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("This view includes fictional demo records."),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Bar chart of artists by genre" }),
  ).toBeVisible();
  await expect(
    page
      .locator("article")
      .filter({ hasText: "Audience metrics" })
      .getByText("Unavailable", { exact: true }),
  ).toBeVisible();
});
test("search opens artist profile and discography", async ({ page }) => {
  await page.goto("/artists");
  await page.getByLabel("Search artist").fill("Velvet");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByText("1–1 of 1")).toBeVisible();
  await page
    .getByRole("link", { name: "Velvet Meridian", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Velvet Meridian", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Discography" }),
  ).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(3);
});
test("selects two artists for comparison without inventing metrics", async ({
  page,
}) => {
  await page.goto("/compare");
  await page.getByLabel("Select Atlas in Bloom").check();
  await page.getByLabel("Select Velvet Meridian").check();
  await page.getByRole("button", { name: "Compare selected (2/5)" }).click();
  await expect(
    page.getByRole("heading", { name: "Artist comparison" }),
  ).toBeVisible();
  await expect(
    page.getByRole("row").filter({ hasText: "Followers" }),
  ).toContainText("Unavailable");
});
test("empty filters and connection errors have useful recovery", async ({
  page,
}) => {
  await page.goto("/artists");
  await page.getByLabel("Search artist").fill("no-match-1234567");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(
    page.getByRole("heading", { name: "No matching records" }),
  ).toBeVisible();
  await page.route("**/api/v1/artists/search?**", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.reload();
  await expect(
    page.getByRole("alert").filter({ hasText: "HTTP 503" }),
  ).toBeVisible();
  await page.unroute("**/api/v1/artists/search?**");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(
    page.getByRole("link", { name: "Velvet Meridian", exact: true }),
  ).toBeVisible();
});
test("Spotify filter never falls back to fictional fixture records", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await page.getByLabel("Source").selectOption("spotify");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(
    page
      .locator("article")
      .filter({ hasText: "Tracked artists" })
      .getByText("0", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("This view includes fictional demo records."),
  ).toHaveCount(0);
  await page.goto("/artists");
  await page.getByLabel("Source").selectOption("spotify");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(
    page.getByRole("heading", { name: "No matching records" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Velvet Meridian", exact: true }),
  ).toHaveCount(0);
});

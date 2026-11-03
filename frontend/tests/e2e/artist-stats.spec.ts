import { test, expect, type Page } from "@playwright/test";

async function openArtist(page: Page) {
  await page.goto("/artists");
  await page.getByLabel("Search artist").fill("Velvet");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await page
    .getByRole("link", { name: "Velvet Meridian", exact: true })
    .click();
  return page.getByRole("region", { name: "Imported catalogue statistics" });
}

test("artist page calculates catalogue counts, duration and yearly releases", async ({
  page,
}) => {
  const stats = await openArtist(page);
  const value = (label: string) =>
    stats
      .locator("dl > div")
      .filter({ has: page.getByText(label, { exact: true }) })
      .locator("dd");
  await expect(value("Release editions")).toHaveText("2");
  await expect(value("Albums")).toHaveText("1");
  await expect(value("Singles & EPs")).toHaveText("1");
  await expect(value("Distinct track IDs")).toHaveText("6");
  await expect(value("Known catalogue duration")).toHaveText("20m 6s");
  await expect(value("Average known track duration")).toHaveText("3m 21s");
  await expect(
    stats.getByText("After the Rain / Velvet Meridian", { exact: false }),
  ).toContainText("2021 (year precision)");
  await expect(
    stats.getByRole("img", { name: "Artist releases by year" }),
  ).toBeVisible();
  await stats.getByText("View yearly release counts").click();
  await expect(
    stats.getByText("2020: 1 releases", { exact: true }),
  ).toBeVisible();
  await expect(
    stats.getByText("2021: 1 releases", { exact: true }),
  ).toBeVisible();
});

test("missing duration remains unavailable while genuine zero is displayed", async ({
  page,
}) => {
  let known = false;
  await page.route("**/catalogue-stats", async (route) => {
    const upstream = await route.fetch();
    const data = await upstream.json();
    await route.fulfill({
      json: {
        ...data,
        known_duration_track_count: known ? 1 : 0,
        known_duration_ms: known ? 0 : null,
        average_known_duration_ms: known ? 0 : null,
      },
    });
  });
  const stats = await openArtist(page);
  const duration = stats
    .locator("dl > div")
    .filter({
      has: page.getByText("Known catalogue duration", { exact: true }),
    })
    .locator("dd");
  await expect(duration).toHaveText("Unavailable");
  known = true;
  await stats.getByRole("button", { name: "Refresh statistics" }).click();
  await expect(duration).toHaveText("0m 0s");
});

test("statistics failure can recover without hiding the artist or discography", async ({
  page,
}) => {
  let fail = true;
  await page.route("**/catalogue-stats", (route) =>
    fail
      ? route.fulfill({ status: 503, json: { detail: "Offline fixture" } })
      : route.continue(),
  );
  const stats = await openArtist(page);
  await expect(stats.getByRole("alert")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Discography", exact: true }),
  ).toBeVisible();
  fail = false;
  await stats.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(stats.getByText("20m 6s", { exact: true })).toBeVisible();
});

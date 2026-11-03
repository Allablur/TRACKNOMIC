import { test, expect } from "@playwright/test";
const token = "offline-ui-token-" + "x".repeat(32);
const artistA = "A".repeat(22),
  artistB = "B".repeat(22);
const batchId = "7b630193-9116-4d42-bb53-340a46ad4d19";
function batch(status = "active", states = ["pending", "pending"]) {
  const counts = {
    pending: 0,
    running: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0,
  };
  const items = states.map((state, index) => {
    counts[state as keyof typeof counts]++;
    return {
      id: `item-${index}`,
      spotify_id: index ? artistB : artistA,
      position: index + 1,
      status: state,
      attempts: state === "pending" ? 0 : 1,
      name: state === "succeeded" ? `Bulk test artist ${index + 1}` : null,
      artist_id:
        state === "succeeded"
          ? `11111111-1111-4111-8111-11111111111${index}`
          : null,
      error: state === "failed" ? "Artist unavailable" : null,
      available_at: new Date().toISOString(),
      last_http_status: state === "succeeded" ? 201 : null,
    };
  });
  return {
    id: batchId,
    name: "Spotify bulk import",
    status,
    server_time: new Date().toISOString(),
    next_attempt_at: null,
    worker_enabled: true,
    total: items.length,
    counts,
    items,
  };
}
async function unlock(page: import("@playwright/test").Page) {
  await page.getByLabel("Ingestion token").fill(token);
  await page.getByRole("button", { name: "Unlock imports" }).click();
  await expect(
    page.getByText("Operator access unlocked for this page session."),
  ).toBeVisible();
}
test("pastes, deduplicates, retries failed entries and reconnects without saving the token", async ({
  page,
}) => {
  let current = batch();
  const submissions: unknown[] = [];
  await page.route("**/api/v1/ingestion/spotify/batches**", async (route) => {
    expect(route.request().headers()["authorization"]).toBe(`Bearer ${token}`);
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/access"))
      return route.fulfill({ json: { configured: true, max_artists: 100 } });
    if (route.request().method() === "POST" && path.endsWith("/batches")) {
      submissions.push(route.request().postDataJSON());
      current = batch("completed", ["succeeded", "failed"]);
      return route.fulfill({ status: 202, json: current });
    }
    if (path.endsWith("/retry")) {
      current = batch("completed", ["succeeded", "succeeded"]);
      return route.fulfill({ json: current });
    }
    return route.fulfill({ json: current });
  });
  await page.goto("/imports");
  await unlock(page);
  await page
    .getByLabel("Artist links")
    .fill(
      `https://open.spotify.com/artist/${artistA}?si=one\nspotify:artist:${artistA}\n${artistB}`,
    );
  await expect(page.getByRole("status")).toContainText(
    "2 unique artists · 1 duplicate rows removed",
  );
  await page.getByRole("button", { name: "Start import (2 artists)" }).click();
  await expect(
    page.getByText("1 imported · 1 failed", { exact: false }),
  ).toBeVisible();
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toMatchObject({ artist_ids: [artistA, artistB] });
  expect(JSON.stringify(submissions[0])).not.toContain(token);
  await page.getByRole("button", { name: "Retry failed artists" }).click();
  await expect(
    page.getByText("2 imported · 0 failed", { exact: false }),
  ).toBeVisible();
  const storage = await page.evaluate(() =>
    JSON.stringify({ ...localStorage }),
  );
  expect(storage).toContain(batchId);
  expect(storage).not.toContain(token);
  await page.reload();
  await expect(page.getByLabel("Ingestion token")).toHaveValue("");
  await expect(
    page.getByText("Bulk test artist 1", { exact: true }),
  ).toHaveCount(0);
  await unlock(page);
  await expect(
    page.getByText("2 imported · 0 failed", { exact: false }),
  ).toBeVisible();
  expect(submissions).toHaveLength(1);
});
test("CSV upload validates rows and supports pause, resume and cancellation", async ({
  page,
}) => {
  let current = batch();
  await page.route("**/api/v1/ingestion/spotify/batches**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/access"))
      return route.fulfill({ json: { configured: true, max_artists: 100 } });
    if (path.endsWith("/pause")) current = batch("paused");
    if (path.endsWith("/resume")) current = batch("active");
    if (path.endsWith("/cancel"))
      current = batch("cancelled", ["cancelled", "cancelled"]);
    return route.fulfill({
      status: path.endsWith("/batches") ? 202 : 200,
      json: current,
    });
  });
  await page.goto("/imports");
  await unlock(page);
  await page.getByLabel("Artist links").fill("invalid link");
  await expect(
    page.getByRole("button", { name: "Start import (0 artists)" }),
  ).toBeDisabled();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Row 1",
  );
  await page.getByLabel("Upload CSV or text file").setInputFiles({
    name: "artists.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      `name,spotify_url\nFirst,https://open.spotify.com/artist/${artistA}\nSecond,spotify:artist:${artistB}\n`,
    ),
  });
  await page.getByRole("button", { name: "Start import (2 artists)" }).click();
  await page.getByRole("button", { name: "Pause queue" }).click();
  await expect(page.getByText("Batch paused", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Resume queue" }).click();
  await expect(page.getByText("Batch active", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cancel remaining" }).click();
  await expect(
    page.getByText("Batch cancelled", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create another batch" }).click();
  await expect(page.getByLabel("Artist links")).toHaveValue("");
});
test("invalid authorization never submits artists", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/v1/ingestion/spotify/batches**", (route) => {
    if (route.request().method() === "POST") writes++;
    return route.fulfill({
      status: 401,
      json: { detail: "Valid ingestion authorization required" },
    });
  });
  await page.goto("/imports");
  await page.getByLabel("Ingestion token").fill("wrong-token");
  await page.getByRole("button", { name: "Unlock imports" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Valid ingestion authorization required",
  );
  await expect(page.getByLabel("Artist links")).toHaveCount(0);
  expect(writes).toBe(0);
});
test("retrying an ambiguous submission reuses its idempotency key", async ({
  page,
}) => {
  const keys: string[] = [];
  await page.route("**/api/v1/ingestion/spotify/batches**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/access"))
      return route.fulfill({ json: { configured: true, max_artists: 100 } });
    if (route.request().method() === "POST") {
      keys.push(route.request().postDataJSON().request_id);
      if (keys.length === 1) return route.abort();
    }
    return route.fulfill({ status: 202, json: batch() });
  });
  await page.goto("/imports");
  await unlock(page);
  await page.getByLabel("Artist links").fill(artistA);
  await page.getByRole("button", { name: "Start import (1 artists)" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "Start import (1 artists)" }).click();
  await expect(page.getByText("Batch active", { exact: true })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

test("bulk input stays within the mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/v1/ingestion/spotify/batches/access", (route) =>
    route.fulfill({ json: { configured: true, max_artists: 100 } }),
  );
  await page.goto("/imports");
  await unlock(page);
  await expect(page.getByLabel("Upload CSV or text file")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

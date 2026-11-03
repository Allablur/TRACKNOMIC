import { chromium } from "@playwright/test";
import { existsSync } from "node:fs";
const browser = await chromium.launch({
  executablePath:
    process.env.CHROMIUM_PATH ||
    (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined),
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1050 },
    reducedMotion: "reduce",
  });
  await page.goto(
    (process.env.FRONTEND_URL || "http://127.0.0.1:3000") + "/dashboard",
  );
  await page.getByText("This view includes fictional demo records.").waitFor();
  await page
    .getByRole("img", { name: "Bar chart of releases by year" })
    .waitFor();
  await page.screenshot({
    path: new URL("../../docs/images/dashboard.png", import.meta.url).pathname,
    fullPage: true,
    animations: "disabled",
  });
  console.log(
    "Saved docs/images/dashboard.png from the running demo application.",
  );
} finally {
  await browser.close();
}

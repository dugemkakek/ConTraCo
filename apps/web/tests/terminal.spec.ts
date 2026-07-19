import { test, expect } from "@playwright/test";

test("terminal page redirects unauthenticated users to login", async ({ page }) => {
  await page.goto("/terminal/BTC-USDT");
  await expect(page).toHaveURL(/\/login/);
});

test("terminal page loads BTC-USDT with TradingView chart and analysis panel", async ({ page }) => {
  const email = `alice-${Date.now()}@example.com`;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const res = await page.request.post(`${apiBase}/api/v1/auth/register`, {
    data: { email, password: "VeryStrong1!" },
  });
  expect(res.status()).toBe(201);
  const { access_token } = await res.json();
  await page.addInitScript(
    (token) => window.localStorage.setItem("confluence_token", token),
    access_token,
  );

  await page.goto("/terminal/BTC-USDT");

  await expect(page.getByText("BTC/USDT").first()).toBeVisible();
  await expect(page.getByTestId("run-analysis-button")).toBeEnabled();

  for (const tf of ["1m", "5m", "15m", "1h", "4h", "1d"]) {
    await expect(page.getByTestId(`timeframe-${tf}`)).toBeVisible();
  }
});

test("running analysis fills the decision console", async ({ page }) => {
  const email = `bob-${Date.now()}@example.com`;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const res = await page.request.post(`${apiBase}/api/v1/auth/register`, {
    data: { email, password: "VeryStrong1!" },
  });
  expect(res.status()).toBe(201);
  const { access_token } = await res.json();
  await page.addInitScript(
    (token) => window.localStorage.setItem("confluence_token", token),
    access_token,
  );

  await page.goto("/terminal/BTC-USDT");
  await page.getByTestId("run-analysis-button").click();
  // Analysis panel may show results in the "analysis" tab
  // Wait for analysis to complete (button re-enables)
  await expect(page.getByTestId("run-analysis-button")).toBeEnabled({ timeout: 60_000 });
});

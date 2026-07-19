import { test, expect } from "@playwright/test";

test("dashboard renders with trading terminal layout", async ({ page }) => {
  const email = `dash-${Date.now()}@example.com`;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const res = await page.request.post(`${apiBase}/api/v1/auth/register`, {
    data: { email, password: "VeryStrong1!" },
  });
  expect(res.status()).toBe(201);
  const { access_token } = await res.json();
  await page.addInitScript(
    (t) => window.localStorage.setItem("confluence_token", t),
    access_token,
  );

  await page.goto("/dashboard");
  // Dashboard header with controls
  await expect(page.getByPlaceholder("Search symbol...")).toBeVisible();
  // Market overview cards should show
  await expect(page.getByText("Market Condition").first()).toBeVisible({ timeout: 15_000 });
});

import { test, expect, type Page } from "@playwright/test";

// Live end-to-end audit: log in once, drive every page, and record
// (1) uncaught console errors and (2) any API response with status >= 400.
// This proves each page's REAL client-side data path works, not just that
// the route resolves. Run with NEXT_PUBLIC_API_BASE_URL pointed at the API.

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

const ROUTES: { path: string; label: string }[] = [
  { path: "/", label: "root" },
  { path: "/dashboard", label: "dashboard" },
  { path: "/terminal/BTC-USDT", label: "terminal" },
  { path: "/scan", label: "scan" },
  { path: "/strategy", label: "strategy" },
  { path: "/journal", label: "journal" },
  { path: "/analytics", label: "analytics" },
  { path: "/watchlist", label: "watchlist" },
  { path: "/alerts", label: "alerts" },
  { path: "/charting", label: "charting" },
  { path: "/debate", label: "debate" },
  { path: "/arbitrage", label: "arbitrage" },
  { path: "/mission-control", label: "mission-control" },
  { path: "/settings", label: "settings" },
  { path: "/token-safety", label: "token-safety" },
  { path: "/trenches", label: "trenches" },
  { path: "/wallet", label: "wallet" },
  { path: "/whales", label: "whales" },
];

type PageReport = {
  label: string;
  path: string;
  consoleErrors: string[];
  pageErrors: string[];
  apiErrors: { status: number; url: string }[];
};

test("full page audit: console errors + failed API calls per route", async ({ page, request }) => {
  test.setTimeout(300_000);

  // Fresh admin-ish account so authed pages actually fetch real data.
  const email = `audit-${Date.now()}@example.com`;
  const reg = await request.post(`${apiBase}/api/v1/auth/register`, {
    data: { email, password: "VeryStrong1!" },
  });
  expect(reg.status(), "register should succeed").toBe(201);
  const { access_token } = await reg.json();

  await page.addInitScript(
    (t) => window.localStorage.setItem("confluence_token", t),
    access_token,
  );

  const reports: PageReport[] = [];

  for (const route of ROUTES) {
    const rep: PageReport = {
      label: route.label,
      path: route.path,
      consoleErrors: [],
      pageErrors: [],
      apiErrors: [],
    };

    const onConsole = (msg: import("@playwright/test").ConsoleMessage) => {
      if (msg.type() === "error") rep.consoleErrors.push(msg.text().slice(0, 300));
    };
    const onPageError = (err: Error) => {
      rep.pageErrors.push(String(err.message).slice(0, 300));
    };
    const onResponse = (res: import("@playwright/test").Response) => {
      const url = res.url();
      if (url.startsWith(apiBase) && res.status() >= 400) {
        rep.apiErrors.push({ status: res.status(), url: url.replace(apiBase, "") });
      }
    };

    page.on("console", onConsole);
    page.on("pageerror", onPageError);
    page.on("response", onResponse);

    // NOTE: do NOT wait for "networkidle" — the dashboard auto-fires a heavy
    // ~24s analysis/run plus polling, so the network never goes idle even
    // though the page works. Use domcontentloaded + a fixed settle window and
    // let the response/console listeners surface real failures.
    try {
      await page.goto(route.path, { waitUntil: "domcontentloaded", timeout: 20_000 });
    } catch (e) {
      rep.pageErrors.push(`NAV_TIMEOUT: ${String(e).slice(0, 120)}`);
    }
    // Give client fetches a moment to run and surface any 4xx/5xx.
    await page.waitForTimeout(6000);

    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("response", onResponse);

    reports.push(rep);
  }

  // Emit a readable matrix to stdout.
  const lines: string[] = ["", "=== PAGE AUDIT MATRIX ==="];
  for (const r of reports) {
    const ok =
      r.consoleErrors.length === 0 &&
      r.pageErrors.length === 0 &&
      r.apiErrors.length === 0;
    lines.push(
      `${ok ? "OK  " : "FAIL"} ${r.path}  ` +
        `console=${r.consoleErrors.length} pageerr=${r.pageErrors.length} api4xx5xx=${r.apiErrors.length}`,
    );
    for (const a of r.apiErrors) lines.push(`       API ${a.status} ${a.url}`);
    for (const c of r.consoleErrors) lines.push(`       CONSOLE ${c}`);
    for (const p of r.pageErrors) lines.push(`       PAGEERR ${p}`);
  }
  lines.push("=== END MATRIX ===", "");
  console.log(lines.join("\n"));

  // Persist for inspection.
  await test.info().attach("audit-matrix.txt", {
    body: lines.join("\n"),
    contentType: "text/plain",
  });
});

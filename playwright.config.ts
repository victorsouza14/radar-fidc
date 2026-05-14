// Playwright config — smoke tests for the static Radar FIDC dashboard.
//
// Serves index.html via `python3 -m http.server 8000` (spawned automatically
// by Playwright on `test`) and walks the 6 dashboard pages plus the global
// trust-bar. Single chromium project keeps CI cheap; cross-browser smokes are
// out of scope for this gate (the app is a static read-only dashboard).
//
// Reporters:
//   - HTML report (always)  → playwright-report/
//   - JSON report (always)  → playwright-report/results.json  (consumed by
//                              scripts/smoke_summary.py + data-refresh workflow)
//   - GitHub annotations    → only when running in CI
//
// JSON is enabled in both environments because scripts/smoke_summary.py is
// the canonical pass/fail bridge for the trust-manifest pipeline.

import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;

const reporters: NonNullable<Parameters<typeof defineConfig>[0]["reporter"]> = [
  ["html", { open: "never", outputFolder: "playwright-report" }],
  ["json", { outputFile: "playwright-report/results.json" }],
];
if (isCI) {
  reporters.push(["github"]);
}

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: isCI ? 1 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: reporters,
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: {
    command: "python3 -m http.server 8000 --bind 127.0.0.1",
    url: "http://127.0.0.1:8000",
    reuseExistingServer: !isCI,
    timeout: 30_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});

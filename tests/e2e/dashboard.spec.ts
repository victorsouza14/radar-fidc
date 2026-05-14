// Smoke tests for the Radar FIDC dashboard.
//
// The dashboard is a single-page static app: index.html ships every <section
// class="page">, and assets/js/router.js toggles `.active` on click of the
// sidebar nav buttons (data-page="overview|fidcs|match|credit"). There is
// no hash routing today, so we navigate by clicking the nav button and
// waiting for the section to gain `.active`.
//
// Each test:
//   1) Boots the app at "/" and waits for the store to hydrate
//      (a known KPI flips from "—" to a numeric value).
//   2) Navigates to the target page via the sidebar.
//   3) Asserts the page rendered without JS errors and that critical
//      data fields are present and free of "NaN"/"undefined".
//
// The standalone "Cenário macroeconômico" and "Clientes" pages were removed
// by product decision: macro indicators now live as KPI cards on the
// overview page (#m-*-overview ids), and clientes data is only consumed
// internally by the match/recommendation engine. data.json still ships
// `clientes` and `macro` blocks for those consumers.
//
// Trust bar and heuristic markers were removed from the frontend by product
// decision. data-quality.json still tracks pipeline_quality_check, freshness,
// and heuristic_fields server-side for auditing, but no UI consumes them.

import { test, expect, type Page } from "@playwright/test";

const NAV = {
  overview: ".nav-btn[data-page=\"overview\"]",
  fidcs:    ".nav-btn[data-page=\"fidcs\"]",
  match:    ".nav-btn[data-page=\"match\"]",
  credit:   ".nav-btn[data-page=\"credit\"]",
} as const;

const SECTION = {
  overview: "#page-overview",
  fidcs:    "#page-fidcs",
  match:    "#page-match",
  credit:   "#page-credit",
} as const;

type PageId = keyof typeof NAV;

const NUMERIC_OR_PCT = /-?\d+(?:[.,]\d+)?\s*%?/;

function expectNoNaN(text: string | null, label: string) {
  expect(text ?? "", `${label}: expected text without NaN/undefined, got "${text}"`).not.toMatch(
    /NaN|undefined/i,
  );
}

/**
 * Boots the app at "/" and waits for it to hydrate. Detects real JS errors
 * via `pageerror` (uncaught exceptions) and console.error, then fails if any
 * occur during boot. Resolves once `#kpi-fundos` (first KPI rendered by
 * overview.init) holds a numeric value, which guarantees the store loaded.
 *
 * Benign browser-injected 404 logs for optional resources (notably
 * `data-quality.json`, which only exists after the trust-manifest pipeline
 * runs locally) are filtered out — they are not script bugs. No UI
 * component consumes the manifest anymore (removed by product decision).
 */
function isBenignConsoleError(text: string, locationUrl: string | undefined): boolean {
  // Chrome surfaces network-level 404s as a generic console.error whose text
  // is "Failed to load resource: the server responded with a status of 404
  // (File not found)". The originating URL lives on the message location, so
  // we only ignore the 404 when it targets a documented optional resource.
  if (!/Failed to load resource.*404/.test(text)) return false;
  if (!locationUrl) return false;
  return /\/data-quality\.json(\?|$)/.test(locationUrl);
}

async function bootDashboard(page: Page): Promise<void> {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    const url = msg.location()?.url;
    if (isBenignConsoleError(text, url)) return;
    errors.push(`console.error: ${text}${url ? ` (from ${url})` : ""}`);
  });

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  // Store has hydrated once the first overview KPI flips from "—" to a number.
  await expect(page.locator("#kpi-fundos")).toHaveText(NUMERIC_OR_PCT, { timeout: 10_000 });

  expect(errors, `JS errors on boot:\n  - ${errors.join("\n  - ")}`).toEqual([]);
}

/**
 * Navigates to a sidebar page and waits for its section to become active.
 * Also waits for `networkidle` because charts may lazy-load assets.
 */
async function gotoTab(page: Page, id: PageId): Promise<void> {
  await page.locator(NAV[id]).click();
  await expect(page.locator(SECTION[id])).toHaveClass(/active/);
  await page.waitForLoadState("networkidle");
}

test.describe("Radar FIDC — smoke", () => {
  test.beforeEach(async ({ page }) => {
    await bootDashboard(page);
  });

  // ─── S1 ───────────────────────────────────────────────────────────────
  test("S1 — Visão Geral renderiza KPIs principais sem NaN", async ({ page }) => {
    await gotoTab(page, "overview");

    // Four headline KPIs on overview: fundos, clientes, empresas, SELIC.
    const kpiIds = ["#kpi-fundos", "#kpi-clientes", "#kpi-empresas", "#kpi-selic"];
    for (const id of kpiIds) {
      const el = page.locator(id);
      await expect(el, `${id} should be visible`).toBeVisible();
      const text = (await el.textContent())?.trim() ?? "";
      expect(text, `${id} should not be the placeholder "—"`).not.toBe("—");
      expect(text, `${id} should not be empty`).not.toBe("");
      expectNoNaN(text, id);
      expect(text, `${id} should contain a digit`).toMatch(/\d/);
    }
  });

  // ─── S2 ───────────────────────────────────────────────────────────────
  test("S2 — Score & Risco (FIDCs) renderiza gráfico e tabela", async ({ page }) => {
    await gotoTab(page, "fidcs");

    // Risco × Retorno scatter mounts to <canvas id="chart-fidcs-scatter">.
    const canvas = page.locator("#page-fidcs canvas").first();
    await expect(canvas, "FIDCs page must render at least one chart canvas").toBeVisible();

    // At least one row in the FIDCs table (data.json ships 1500 fidcs).
    const rows = page.locator("#tbody-fidcs tr");
    await expect.poll(async () => rows.count(), {
      message: "FIDCs table must have at least one row",
      timeout: 5_000,
    }).toBeGreaterThanOrEqual(1);

    // The count badge in the card title acts as a legend for the selection.
    const count = page.locator("#fidcs-count");
    await expect(count).toBeVisible();
    expectNoNaN(await count.textContent(), "#fidcs-count");
  });

  // ─── S3 ───────────────────────────────────────────────────────────────
  test("S3 — Visão geral mostra CDI + IPCA macro KPIs sem NaN", async ({ page }) => {
    await gotoTab(page, "overview");

    // Macro strip in overview (4 indicators, agrupados em uma única caixa).
    // SELIC atual já vive nos KPIs principais do topo (#kpi-selic) — não
    // duplicamos no strip macro.
    const macroIds = [
      "#m-cdi-overview",
      "#m-ipca-overview",
      "#m-selic-proj-overview",
      "#m-ipca-proj-overview",
    ];
    for (const id of macroIds) {
      const el = page.locator(id);
      await expect(el, `${id} should be visible`).toBeVisible();
      const text = ((await el.textContent()) ?? "").trim();
      expectNoNaN(text, id);
      expect(text, `${id} should not be the placeholder "—"`).not.toBe("—");
      expect(
        /^-?\d+([.,]\d+)?\s*%?$/.test(text),
        `${id} must match /^-?\\d+([.,]\\d+)?\\s*%?$/, got "${text}"`,
      ).toBe(true);
    }
  });

  // ─── S4 ───────────────────────────────────────────────────────────────
  test("S4 — Match exibe tabela top-3 ou empty-state com sugestões", async ({ page }) => {
    await gotoTab(page, "match");

    const tbody = page.locator("#tbody-match");
    await expect(tbody).toBeVisible();

    const rows = tbody.locator("tr");
    const emptyCell = tbody.locator('[data-empty-state="true"]');
    const cards = page.locator("#match-cards .pme-card");

    const rowCount = await rows.count();
    const emptyCount = await emptyCell.count();
    const cardCount = await cards.count();

    expect(
      rowCount > 0 || emptyCount > 0 || cardCount > 0,
      `Match page must show table rows (${rowCount}), cards (${cardCount}) or empty-state (${emptyCount})`,
    ).toBe(true);

    // Client selector must be populated (proves init() ran).
    const select = page.locator("#f-match-cliente");
    await expect(select).toBeVisible();
    const optionCount = await select.locator("option").count();
    expect(optionCount, "Client select must have placeholder + at least one client").toBeGreaterThanOrEqual(2);
  });

  // ─── S5 ───────────────────────────────────────────────────────────────
  test("S5 — Credit mostra KPIs numéricos e tabela de empresas", async ({ page }) => {
    await gotoTab(page, "credit");

    // Headline KPI (empresas avaliadas) must be numeric and non-zero shape.
    const total = page.locator("#kr-total");
    await expect(total).toBeVisible();
    const totalText = ((await total.textContent()) ?? "").trim();
    expectNoNaN(totalText, "#kr-total");
    expect(totalText, "#kr-total must contain a digit").toMatch(/\d/);
    expect(totalText, "#kr-total must not be the placeholder").not.toBe("—");

    // Table of empresas: at least one row (data.json ships 489 empresas).
    const rows = page.locator("#tbody-credit tr");
    await expect.poll(async () => rows.count(), {
      message: "Credit table must have at least one row",
      timeout: 5_000,
    }).toBeGreaterThanOrEqual(1);

    // Risk-distribution donut canvas must mount.
    const donut = page.locator("#chart-credit-donut");
    await expect(donut).toBeVisible();
  });

});

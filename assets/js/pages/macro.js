// Página Cenário Macro.
//   init:  KPIs textuais + texto do cenário.
//   mount: charts comparativos.

import { Store } from "../store.js";
import { fmtPct } from "../utils/format.js";
import { setText } from "../utils/dom.js";
import { verticalBar } from "../components/chart-factory.js";

const MACRO_COLORS = ["#093A1B", "#1F8045", "#E8A33D", "#2563EB", "#B45309"];
const INAD_COLORS  = ["#C0392B", "#E8A33D", "#1F8045", "#2563EB"];

function renderHeader() {
  const m = Store.macro();
  setText("m-selic",      fmtPct(m.selic));
  setText("m-cdi",        fmtPct(m.cdi));
  setText("m-ipca",       fmtPct(m.ipca, 2));
  setText("m-selic-proj", fmtPct(m.selic_proj));

  setText("cenario-desc",
    `Cenário atual: ${(m.cenario || "").replace(/_/g, " ").toUpperCase()}. ${m.descricao || ""}`);
}

function renderCharts() {
  const m = Store.macro();
  verticalBar(
    "chart-macro-bar",
    ["SELIC", "CDI", "IPCA 12m", "SELIC proj.", "IPCA proj."],
    [m.selic, m.cdi, m.ipca, m.selic_proj, m.ipca_proj].map(v => v ?? 0),
    MACRO_COLORS,
    raw => `${Number(raw).toFixed(2)}%`,
  );

  verticalBar(
    "chart-inad",
    ["Inadimplência PJ", "Inadimplência PF", "IBC-Br", "Dólar venda (R$)"],
    [m.inadimplencia_pj, m.inadimplencia_pf, m.ibc_br, m.dolar_venda].map(v => v ?? 0),
    INAD_COLORS,
    raw => `${Number(raw).toFixed(2)}`,
  );
}

export function init() { renderHeader(); }
export function mount() { renderCharts(); }

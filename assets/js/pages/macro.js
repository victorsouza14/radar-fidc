import { Store } from "../store.js";
import { fmtPct } from "../utils/format.js";
import { setText } from "../utils/dom.js";
import { verticalBar } from "../components/chart-factory.js";
import { tokenColor } from "../ui.js";

const macroColors = () => [
  tokenColor("--data-accent"),
  tokenColor("--data-positive"),
  tokenColor("--data-warning"),
  tokenColor("--data-info"),
  tokenColor("--data-neutral"),
];
const inadColors = () => [
  tokenColor("--data-negative"),
  tokenColor("--data-warning"),
  tokenColor("--data-positive"),
  tokenColor("--data-info"),
];

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
    macroColors(),
    raw => `${Number(raw).toFixed(2)}%`,
  );

  verticalBar(
    "chart-inad",
    ["Inadimplência PJ", "Inadimplência PF", "IBC-Br", "Dólar venda (R$)"],
    [m.inadimplencia_pj, m.inadimplencia_pf, m.ibc_br, m.dolar_venda].map(v => v ?? 0),
    inadColors(),
    raw => `${Number(raw).toFixed(2)}`,
  );
}

export function init() { renderHeader(); }
export function mount() { renderCharts(); }

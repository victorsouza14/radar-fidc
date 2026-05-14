import { Store } from "../store.js";
import { fmtPct } from "../utils/format.js";
import { setText, byId } from "../utils/dom.js";
import { verticalBar } from "../components/chart-factory.js";
import { tokenColor } from "../ui.js";
import { markHeuristic } from "../utils/trust.js";

// SELIC é o único verde — as demais usam tons distintos pra evitar
// confundir métricas que andam correlacionadas (SELIC e CDI).
const macroColors = () => [
  tokenColor("--data-accent"),    // SELIC      — verde
  tokenColor("--data-info"),      // CDI        — azul
  tokenColor("--data-warning"),   // IPCA 12m   — âmbar
  tokenColor("--data-negative"),  // SELIC*     — coral
  tokenColor("--data-neutral"),   // IPCA*      — cinza
];
const inadColors = () => [
  tokenColor("--data-negative"),
  tokenColor("--data-warning"),
  tokenColor("--data-positive"),
  tokenColor("--data-info"),
];

// Labels curtos no eixo X (caber em viewport estreita sem rotação que
// atropela as barras); nome completo aparece no tooltip ao hover.
// `fmt(v)` formata o valor da barra no tooltip de forma específica
// pra cada métrica (% sufixo, R$ prefixo, índice sem unidade).
const pct = (v) => `${Number(v).toFixed(2)}%`;
const brl = (v) => `R$ ${Number(v).toFixed(2).replace(".", ",")}`;
const idx = (v) => Number(v).toFixed(2);

const MACRO_BARS = [
  { label: "SELIC",    full: "SELIC",                 fmt: pct, get: m => m.selic },
  { label: "CDI",      full: "CDI",                   fmt: pct, get: m => m.cdi },
  { label: "IPCA 12m", full: "IPCA acumulado 12m",    fmt: pct, get: m => m.ipca },
  { label: "SELIC*",   full: "SELIC projetada (12m)", fmt: pct, get: m => m.selic_proj },
  { label: "IPCA*",    full: "IPCA projetada (12m)",  fmt: pct, get: m => m.ipca_proj },
];

const INAD_BARS = [
  { label: "Inad. PJ", full: "Inadimplência PJ",   fmt: pct, get: m => m.inadimplencia_pj },
  { label: "Inad. PF", full: "Inadimplência PF",   fmt: pct, get: m => m.inadimplencia_pf },
  { label: "IBC-Br",   full: "IBC-Br (atividade)", fmt: idx, get: m => m.ibc_br },
  { label: "Dólar",    full: "Dólar venda",        fmt: brl, get: m => m.dolar_venda },
];

async function renderHeader() {
  const m = Store.macro();
  setText("m-selic", fmtPct(m.selic));
  setText("m-cdi",   fmtPct(m.cdi));
  setText("m-ipca",  fmtPct(m.ipca, 2));

  // SELIC* e IPCA* são heurísticas — pedimos ao trust manifest o badge
  // inline. Quando a fonte oficial substituir a heurística (Fase 3), o
  // helper retorna "" e o badge some sem mudança de código aqui.
  const [selicProjMark, ipcaProjMark] = await Promise.all([
    markHeuristic("macro.selic_proj"),
    markHeuristic("macro.ipca_proj"),
  ]);

  const elSelicProj = byId("m-selic-proj");
  if (elSelicProj) {
    elSelicProj.innerHTML = `${fmtPct(m.selic_proj)}${selicProjMark}`;
  }

  const elIpcaProj = byId("m-ipca-proj");
  if (elIpcaProj) {
    elIpcaProj.innerHTML = `${fmtPct(m.ipca_proj)}${ipcaProjMark}`;
  }

  setText("cenario-desc",
    `Cenário atual: ${(m.cenario || "").replace(/_/g, " ").toUpperCase()}. ${m.descricao || ""}`);
}

// Tooltip mostra o nome COMPLETO de cada coluna + valor formatado pela
// função específica da métrica (% / R$ / índice). Eixo X só com label curto.
function renderBar(canvasId, schema, colors) {
  const m = Store.macro();
  const labels = schema.map(b => b.label);
  const data   = schema.map(b => b.get(m) ?? 0);
  verticalBar(canvasId, labels, data, colors, (raw, ctx) => {
    const item = schema[ctx.dataIndex];
    return `${item.full}: ${item.fmt(raw)}`;
  });
}

function renderCharts() {
  renderBar("chart-macro-bar", MACRO_BARS, macroColors());
  renderBar("chart-inad",      INAD_BARS,  inadColors());
}

export async function init() { await renderHeader(); }
export function mount() { renderCharts(); }

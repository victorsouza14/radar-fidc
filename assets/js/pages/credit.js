import { Store } from "../store.js";
import { fmtInt, fmtNum, fmtPct, escapeHTML } from "../utils/format.js";
import { setText, byId, onInput, onChange, onClick, resetField } from "../utils/dom.js";
import { memoize } from "../utils/memo.js";
import { riscoColor, riscoBadge } from "../theme.js";
import { doughnut } from "../components/chart-factory.js";
import { createPaginatedTable } from "../components/paginated-table.js";

const RISCO_ORDER = ["BAIXO", "MEDIO", "ALTO"];

// Filtros numéricos: `null` = inativo. Score/prob default só se aplicam a
// empresas com `dados_suficientes=true` (score não é comparável quando
// derivado de < MIN_BOLETOS_SCORE_CONFIAVEL boletos). Filtro de boletos
// se aplica a todas as empresas, independentemente da suficiência.
const state = {
  busca: "",
  risco: "",
  scoreMin: null,
  scoreMax: null,
  probMin: null,
  probMax: null,
  boletosMin: null,
  boletosMax: null,
};

const inRange = (v, lo, hi) => {
  if (v == null) return false;
  if (lo != null && v < lo) return false;
  if (hi != null && v > hi) return false;
  return true;
};

const applyFilters = memoize((s) => {
  const buscaLc = s.busca.toLowerCase();
  const all = Store.credit.empresas();
  const hasScoreFilter   = s.scoreMin   != null || s.scoreMax   != null;
  const hasProbFilter    = s.probMin    != null || s.probMax    != null;
  const hasBoletosFilter = s.boletosMin != null || s.boletosMax != null;

  const out = [];
  for (let i = 0; i < all.length; i++) {
    const e = all[i];
    if (buscaLc && !(e.nome ?? "").toLowerCase().includes(buscaLc)) continue;
    if (s.risco && e.risco !== s.risco) continue;

    // Score/prob default só são comparáveis para empresas com dados suficientes.
    // Quando o usuário aplica esses filtros, empresas insuficientes ficam de fora.
    if (hasScoreFilter) {
      if (!e.dados_suficientes) continue;
      if (!inRange(e.score, s.scoreMin, s.scoreMax)) continue;
    }
    if (hasProbFilter) {
      if (!e.dados_suficientes) continue;
      if (!inRange(e.prob_default, s.probMin, s.probMax)) continue;
    }
    if (hasBoletosFilter && !inRange(e.total_boletos, s.boletosMin, s.boletosMax)) continue;

    out.push(e);
  }
  return out;
}, s => [
  s.busca, s.risco,
  s.scoreMin, s.scoreMax,
  s.probMin, s.probMax,
  s.boletosMin, s.boletosMax,
].join("|"));

const INSUFICIENTE_HTML = `<span class="badge-dados-insuficientes">Dados insuficientes</span>`;

const rowTpl = (e) => {
  const scoreCell = e.dados_suficientes
    ? `<strong>${fmtNum(e.score)}</strong>`
    : INSUFICIENTE_HTML;
  const probCell  = e.dados_suficientes
    ? fmtPct((e.prob_default ?? 0) * 100, 2)
    : "—";
  return `
    <tr>
      <td>${escapeHTML(e.nome)}</td>
      <td>${scoreCell}</td>
      <td>${probCell}</td>
      <td><span class="badge ${riscoBadge(e.risco)}">${escapeHTML(e.risco)}</span></td>
      <td>${fmtInt(e.total_boletos)}</td>
      <td>${fmtInt(e.n_default)}</td>
      <td>${fmtPct((e.pct_default ?? 0) * 100, 1)}</td>
    </tr>`;
};

const table = createPaginatedTable({
  prefix: "credit",
  tbodyId: "tbody-credit",
  rowTpl,
  colspan: 7,
  empty: "Nenhuma empresa encontrada",
  noun: "empresas",
  keyField: "nome",
  onUpdate: (page) => {
    const label = page.total === 1 ? "empresa na amostra" : "empresas na amostra";
    setText("credit-count", `${page.total.toLocaleString("pt-BR")} ${label}`);
  },
});

function renderKPIs() {
  const s = Store.credit.stats();
  const total = s.total || 1;
  const baixo = s.por_risco?.BAIXO ?? 0;
  const medio = s.por_risco?.MEDIO ?? 0;
  const alto  = s.por_risco?.ALTO  ?? 0;

  setText("kr-total", fmtInt(s.total));
  setText("kr-baixo", fmtInt(baixo));
  setText("kr-medio", fmtInt(medio));
  setText("kr-alto",  fmtInt(alto));

  setText("kr-baixo-pct", `${((baixo / total) * 100).toFixed(1)}%`);
  setText("kr-medio-pct", `${((medio / total) * 100).toFixed(1)}%`);
  setText("kr-alto-pct",  `${((alto  / total) * 100).toFixed(1)}%`);
}

function renderDonut() {
  const s = Store.credit.stats();
  const labels = RISCO_ORDER.filter(k => s.por_risco?.[k]);
  doughnut(
    "chart-credit-donut", labels,
    labels.map(k => s.por_risco[k]),
    labels.map(k => riscoColor(k)),
    s.total,
  );
}

function onStateChange() {
  table.reset();
  table.render(applyFilters(state));
}

// Converte input numérico em number ou null (input vazio = filtro inativo).
// Inválidos (NaN) também viram null pra não derrubar a tabela.
const numOrNull = (v) => {
  if (v === "" || v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

function bindFilters() {
  onInput("f-credit-busca",        v => { state.busca      = v;              onStateChange(); });
  onChange("f-credit-risco",       v => { state.risco      = v;              onStateChange(); });
  onInput("f-credit-score-min",    v => { state.scoreMin   = numOrNull(v);   onStateChange(); });
  onInput("f-credit-score-max",    v => { state.scoreMax   = numOrNull(v);   onStateChange(); });
  onInput("f-credit-prob-min",     v => { state.probMin    = numOrNull(v);   onStateChange(); });
  onInput("f-credit-prob-max",     v => { state.probMax    = numOrNull(v);   onStateChange(); });
  onInput("f-credit-boletos-min",  v => { state.boletosMin = numOrNull(v);   onStateChange(); });
  onInput("f-credit-boletos-max",  v => { state.boletosMax = numOrNull(v);   onStateChange(); });

  onClick("f-credit-clear", () => {
    state.busca = ""; state.risco = "";
    state.scoreMin = state.scoreMax = null;
    state.probMin = state.probMax = null;
    state.boletosMin = state.boletosMax = null;
    // Reset busca + risco (texto/select); demais inputs limpos via byId.value.
    resetField("f-credit-busca");
    resetField("f-credit-risco");
    ["f-credit-score-min", "f-credit-score-max",
     "f-credit-prob-min",  "f-credit-prob-max",
     "f-credit-boletos-min", "f-credit-boletos-max"].forEach(id => {
      const el = byId(id);
      if (el) el.value = "";
    });
    onStateChange();
  });
}

export function init() {
  renderKPIs();
  table.render(applyFilters(state));
  bindFilters();
}

export function mount() {
  renderDonut();
}

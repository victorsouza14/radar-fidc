import { Store } from "../store.js";
import { fmtNum, fmtPct, escapeHTML } from "../utils/format.js";
import { setText, onInput, onChange, onClick, resetField, debounce } from "../utils/dom.js";
import { memoize } from "../utils/memo.js";
import { riscoBadge, riscoColor, perfilColor, RISCO_ORDER_FULL } from "../theme.js";
import { scatterLogY } from "../components/chart-factory.js";
import { createPaginatedTable } from "../components/paginated-table.js";

let _mounted = false;

const state = { busca: "", risco: "", cota: "", perfil: "" };
const stateKey = (s) => `${s.busca}|${s.risco}|${s.cota}|${s.perfil}`;

const applyFilters = memoize((s) => {
  const buscaLc = s.busca.toLowerCase();
  const all = Store.fidcs.detalhe();
  const out = [];
  for (let i = 0; i < all.length; i++) {
    const f = all[i];
    if (buscaLc && !f.fundo.toLowerCase().includes(buscaLc) && !f.cnpj.includes(buscaLc)) continue;
    if (s.risco  && f.risco !== s.risco) continue;
    if (s.cota   && f.tipo_cota !== s.cota) continue;
    if (s.perfil && f.perfil_sugerido !== s.perfil) continue;
    out.push(f);
  }
  return out;
}, stateKey);

const rowTpl = (f) => `
  <tr>
    <td class="cell-truncate" title="${escapeHTML(f.fundo)}">${escapeHTML(f.fundo)}</td>
    <td>${escapeHTML(f.tipo_cota)}</td>
    <td><span class="badge ${riscoBadge(f.risco)}">${escapeHTML(f.risco)}</span></td>
    <td>${fmtNum(f.score_risco)}</td>
    <td><span style="color:${perfilColor(f.perfil_sugerido)};font-weight:600;font-size:0.78rem">${escapeHTML(f.perfil_sugerido)}</span></td>
    <td><strong>${fmtPct(f.retorno_anual, 2)}</strong></td>
    <td>${fmtPct(f.volatilidade, 2)}</td>
    <td>${fmtPct(f.taxa_inad, 2)}</td>
    <td>${f.meses_historico}m</td>
  </tr>`;

const table = createPaginatedTable({
  prefix: "fidcs",
  tbodyId: "tbody-fidcs",
  rowTpl,
  colspan: 9,
  empty: "Nenhum FIDC corresponde aos filtros",
  noun: "fundos",
  keyField: "cnpj",
  onUpdate: (page) => {
    const label = page.total === 1 ? "FIDC encontrado" : "FIDCs encontrados";
    setText("fidcs-count", `${page.total.toLocaleString("pt-BR")} ${label}`);
  },
});

function percentile(sorted, p) {
  if (!sorted.length) return null;
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

// IQR (Tukey 1.5×): remove valores fora de [Q1-1.5·IQR, Q3+1.5·IQR].
// Amostras < 4 são pequenas demais para a estatística — devolve cru.
function withoutOutliers(items, field) {
  const values = [];
  for (const it of items) {
    const v = it[field];
    if (typeof v === "number" && !Number.isNaN(v)) values.push(v);
  }
  if (values.length < 4) return values;
  values.sort((a, b) => a - b);
  const q1 = percentile(values, 0.25);
  const q3 = percentile(values, 0.75);
  const iqr = q3 - q1;
  const lo = q1 - 1.5 * iqr;
  const hi = q3 + 1.5 * iqr;
  return values.filter(v => v >= lo && v <= hi);
}

function statsFromValues(values) {
  if (!values.length) return { min: null, max: null, avg: null };
  let min = values[0], max = values[0], sum = 0;
  for (const v of values) {
    if (v < min) min = v;
    if (v > max) max = v;
    sum += v;
  }
  return { min, max, avg: sum / values.length };
}

function renderStats(filtered) {
  const fmt = (v, d = 2) => v == null ? "—" : v.toFixed(d);
  // Retorno descarta negativos antes do IQR — perdas históricas distorcem
  // o mínimo e o produto pede apenas o intervalo positivo.
  const positivos = filtered.filter(
    f => typeof f.retorno_anual === "number" && f.retorno_anual > 0,
  );
  const ret = statsFromValues(withoutOutliers(positivos, "retorno_anual"));
  setText("fidcs-stat-retorno-max", fmt(ret.max));
  setText("fidcs-stat-retorno-min", fmt(ret.min));

  const vol   = statsFromValues(withoutOutliers(filtered, "volatilidade"));
  const inad  = statsFromValues(withoutOutliers(filtered, "taxa_inad"));
  const score = statsFromValues(withoutOutliers(filtered, "score_risco"));
  setText("fidcs-stat-vol",   fmt(vol.avg));
  setText("fidcs-stat-inad",  fmt(inad.avg));
  setText("fidcs-stat-score", fmt(score.avg, 1));
}

function renderScatter(filtered) {
  if (!_mounted) return;
  // Agrupa por risco — cada classe vira dataset distinto (legend separa).
  const buckets = Object.create(null);
  for (const r of RISCO_ORDER_FULL) buckets[r] = [];
  for (const f of filtered) {
    const r = RISCO_ORDER_FULL.includes(f.risco) ? f.risco : "SEM DADOS";
    buckets[r].push({
      x: f.score_risco,
      y: f.retorno_anual,
      meta: { nome: f.fundo, cota: f.tipo_cota, vol: f.volatilidade, inad: f.taxa_inad },
    });
  }
  const groups = RISCO_ORDER_FULL
    .filter(r => buckets[r].length > 0)
    .map(r => ({ label: r, color: riscoColor(r), points: buckets[r] }));

  scatterLogY({
    id: "chart-fidcs-scatter",
    groups,
    xLabel: "Score risco (0-100)",
    yLabel: "Retorno a.a. (%) — escala log",
    tooltipLabel: (p) => {
      const m = p.meta || {};
      return ` ${m.nome ?? ""} — risco ${p.x?.toFixed?.(1)} · retorno ${p.y?.toFixed?.(2)}%`;
    },
  });
}

const scheduleChart = debounce((filtered) => {
  if (!_mounted) return;
  requestAnimationFrame(() => renderScatter(filtered));
}, 120);

function onStateChange() {
  table.reset();
  const filtered = applyFilters(state);
  table.render(filtered);
  renderStats(filtered);
  scheduleChart(filtered);
}

function bindFilters() {
  onInput("f-fidc-busca",   v => { state.busca  = v; onStateChange(); });
  onChange("f-fidc-risco",  v => { state.risco  = v; onStateChange(); });
  onChange("f-fidc-cota",   v => { state.cota   = v; onStateChange(); });
  onChange("f-fidc-perfil", v => { state.perfil = v; onStateChange(); });
  onClick("f-fidc-clear", () => {
    state.busca = state.risco = state.cota = state.perfil = "";
    ["f-fidc-busca", "f-fidc-risco", "f-fidc-cota", "f-fidc-perfil"].forEach(id => resetField(id));
    onStateChange();
  });
}

export function init() {
  const filtered = applyFilters(state);
  table.render(filtered);
  renderStats(filtered);
  bindFilters();
}

export function mount() {
  _mounted = true;
  renderScatter(applyFilters(state));
}

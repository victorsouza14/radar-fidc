import { Store } from "../store.js";
import { fmtNum, fmtPct, escapeHTML } from "../utils/format.js";
import { setText, onInput, onChange, onClick, resetField, debounce } from "../utils/dom.js";
import { memoize } from "../utils/memo.js";
import { riscoBadge, perfilColor, cotaColor } from "../theme.js";
import { pie } from "../components/chart-factory.js";
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

function average(items, field) {
  if (!items.length) return null;
  let sum = 0, count = 0;
  for (const it of items) {
    const v = it[field];
    if (typeof v === "number" && !Number.isNaN(v)) { sum += v; count++; }
  }
  return count ? sum / count : null;
}

function renderStats(filtered) {
  const fmt = (v, d = 2) => v == null ? "—" : v.toFixed(d);
  setText("fidcs-stat-retorno", fmt(average(filtered, "retorno_anual")));
  setText("fidcs-stat-vol",     fmt(average(filtered, "volatilidade")));
  setText("fidcs-stat-inad",    fmt(average(filtered, "taxa_inad")));
  setText("fidcs-stat-score",   fmt(average(filtered, "score_risco"), 1));
}

function renderPieCotas(filtered) {
  const count = Object.create(null);
  for (const f of filtered) count[f.tipo_cota] = (count[f.tipo_cota] || 0) + 1;
  const keys = Object.keys(count);
  pie("chart-cota", keys, keys.map(k => count[k]), keys.map(cotaColor));
}

const scheduleChart = debounce((filtered) => {
  if (!_mounted) return;
  requestAnimationFrame(() => renderPieCotas(filtered));
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
  renderPieCotas(applyFilters(state));
}

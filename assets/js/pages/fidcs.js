import { Store } from "../store.js";
import { fmtNum, fmtPct, escapeHTML } from "../utils/format.js";
import { setText, onInput, onChange, onClick, resetField, debounce } from "../utils/dom.js";
import { memoize } from "../utils/memo.js";
import { riscoColor, riscoBadge, perfilColor, cotaColor } from "../theme.js";
import { scatter, pie } from "../components/chart-factory.js";
import { renderTable } from "../components/table.js";

const RETORNO_MIN = -50;
const RETORNO_MAX = 200;
const TABLE_LIMIT = 200;
const SCATTER_MAX = 400;

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
    <td style="font-weight:500;font-size:0.82rem">${escapeHTML(f.fundo)}</td>
    <td>${escapeHTML(f.tipo_cota)}</td>
    <td><span class="badge ${riscoBadge(f.risco)}">${escapeHTML(f.risco)}</span></td>
    <td>${fmtNum(f.score_risco)}</td>
    <td><span style="color:${perfilColor(f.perfil_sugerido)};font-weight:600;font-size:0.78rem">${escapeHTML(f.perfil_sugerido)}</span></td>
    <td><strong>${fmtPct(f.retorno_anual, 2)}</strong></td>
    <td>${fmtPct(f.volatilidade, 2)}</td>
    <td>${fmtPct(f.taxa_inad, 2)}</td>
    <td>${f.meses_historico}m</td>
  </tr>`;

function renderTabela(filtered) {
  setText("fidcs-count",
    `${filtered.length} FIDC${filtered.length === 1 ? "" : "s"} encontrado${filtered.length === 1 ? "" : "s"}`);
  renderTable("tbody-fidcs", filtered, rowTpl, {
    limit: TABLE_LIMIT, colspan: 9, empty: "Nenhum FIDC corresponde aos filtros",
  });
}

function renderScatter(filtered) {
  const pool = [];
  for (let i = 0; i < filtered.length; i++) {
    const f = filtered[i];
    if (f.retorno_anual >= RETORNO_MIN && f.retorno_anual <= RETORNO_MAX) {
      pool.push({
        x: f.score_risco, y: f.retorno_anual,
        nome: f.fundo, risco: f.risco, cota: f.tipo_cota, perfil: f.perfil_sugerido,
      });
    }
  }
  const step = pool.length > SCATTER_MAX ? Math.ceil(pool.length / SCATTER_MAX) : 1;
  const points = step > 1 ? pool.filter((_, i) => i % step === 0) : pool;

  scatter(
    "chart-scatter", points,
    p => riscoColor(p.risco),
    p => [
      ` ${p.nome.slice(0, 55)}`,
      ` Risco: ${p.risco} (${fmtNum(p.x)})`,
      ` Retorno: ${fmtPct(p.y, 2)}`,
      ` ${p.cota} • ${p.perfil}`,
    ],
  );
}

function renderPieCotas(filtered) {
  const cotaCount = Object.create(null);
  for (let i = 0; i < filtered.length; i++) {
    const c = filtered[i].tipo_cota;
    cotaCount[c] = (cotaCount[c] || 0) + 1;
  }
  const keys = Object.keys(cotaCount);
  pie("chart-cota", keys, keys.map(k => cotaCount[k]), keys.map(k => cotaColor(k)));
}

// Tabela render imediato; charts debounce+rAF para não bloquear typing nos filtros.
const scheduleCharts = debounce((filtered) => {
  if (!_mounted) return;
  requestAnimationFrame(() => {
    renderScatter(filtered);
    renderPieCotas(filtered);
  });
}, 120);

function onStateChange() {
  const filtered = applyFilters(state);
  renderTabela(filtered);
  scheduleCharts(filtered);
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
  renderTabela(applyFilters(state));
  bindFilters();
}

export function mount() {
  _mounted = true;
  const filtered = applyFilters(state);
  renderScatter(filtered);
  renderPieCotas(filtered);
}

import { Store } from "../store.js";
import { fmtInt, fmtNum, fmtPct, escapeHTML } from "../utils/format.js";
import { setText, onInput, onChange } from "../utils/dom.js";
import { memoize } from "../utils/memo.js";
import { riscoColor, riscoBadge } from "../theme.js";
import { doughnut } from "../components/chart-factory.js";
import { renderTable } from "../components/table.js";

const RISCO_ORDER = ["BAIXO", "MEDIO", "ALTO"];

const state = { busca: "", risco: "" };

const applyFilters = memoize((s) => {
  const buscaLc = s.busca.toLowerCase();
  const all = Store.credit.empresas();
  const out = [];
  for (let i = 0; i < all.length; i++) {
    const e = all[i];
    if (buscaLc && !e.id_cnpj.toLowerCase().includes(buscaLc)) continue;
    if (s.risco && e.risco !== s.risco) continue;
    out.push(e);
  }
  return out;
}, s => `${s.busca}|${s.risco}`);

const rowTpl = (e) => `
  <tr>
    <td style="font-family:monospace;font-size:0.74rem;color:var(--fg-subtle)">${escapeHTML(e.id_cnpj)}</td>
    <td><strong>${fmtNum(e.score)}</strong></td>
    <td>${fmtPct((e.prob_default ?? 0) * 100, 2)}</td>
    <td><span class="badge ${riscoBadge(e.risco)}">${escapeHTML(e.risco)}</span></td>
    <td>${fmtInt(e.total_boletos)}</td>
    <td>${fmtInt(e.n_default)}</td>
    <td>${fmtPct((e.pct_default ?? 0) * 100, 1)}</td>
  </tr>`;

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

function renderTabela() {
  const filtered = applyFilters(state);
  setText("credit-count", `${filtered.length} empresas na amostra`);
  renderTable("tbody-credit", filtered, rowTpl,
    { colspan: 7, empty: "Nenhuma empresa encontrada" });
}

function bindFilters() {
  onInput("f-credit-busca",  v => { state.busca = v; renderTabela(); });
  onChange("f-credit-risco", v => { state.risco = v; renderTabela(); });
}

export function init() {
  renderKPIs();
  renderTabela();
  bindFilters();
}

export function mount() {
  renderDonut();
}

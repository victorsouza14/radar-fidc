import { Store } from "../store.js";
import { fmtNum, fmtPct, escapeHTML } from "../utils/format.js";
import { setText, setHTML, byId, onChange, onClick, resetField } from "../utils/dom.js";
import { memoize } from "../utils/memo.js";
import { perfilColor, riscoBadge, rankBadgeClass } from "../theme.js";
import { createPaginatedTable } from "../components/paginated-table.js";

const TOP_N = 5;

const state = { cpf: "", perfil: "" };

const applyFilters = memoize((s) => {
  return Store.matches.lista()
    .filter(m => {
      if (s.cpf && m.cpf !== s.cpf) return false;
      if (s.perfil && m.perfil_cliente !== s.perfil) return false;
      return true;
    })
    .sort((a, b) => a.cpf.localeCompare(b.cpf) || a.rank - b.rank);
}, s => `${s.cpf}|${s.perfil}`);

function clientHeaderTpl(c) {
  return `
    <div class="card" style="margin-bottom:24px">
      <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap">
        <div style="flex:1;min-width:240px">
          <div style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--fg-subtle);font-weight:600">Cliente selecionado</div>
          <div style="font-size:1.5rem;font-weight:700;color:var(--fg);margin-top:4px">${escapeHTML(c.nome)}</div>
          <div style="font-size:0.85rem;color:var(--fg-subtle);margin-top:4px">${c.idade} anos · ${escapeHTML(c.email)}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--fg-subtle);font-weight:600">Perfil suitability</div>
          <div style="font-size:1.4rem;font-weight:800;color:${perfilColor(c.perfil)};margin-top:4px">${escapeHTML(c.perfil)}</div>
          <div style="font-size:0.85rem;color:var(--fg-subtle)">Score ${fmtNum(c.score_perfil)}</div>
        </div>
      </div>
    </div>`;
}

function matchCardTpl(m) {
  return `
    <div class="pme-card">
      <div class="pme-rank">Recomendação #${m.rank} · match ${fmtNum(m.match_score)}</div>
      <div class="pme-nome">${escapeHTML(m.fundo)}</div>
      <div class="pme-meta">
        <div class="pme-score">${fmtNum(m.match_score)}</div>
        <span class="badge ${riscoBadge(m.risco_fundo)}">${escapeHTML(m.risco_fundo)}</span>
        <span style="font-size:0.82rem;color:var(--fg-subtle)">${escapeHTML(m.tipo_cota)}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.78rem;color:var(--fg-muted);margin-bottom:12px">
        <div>Retorno: <strong>${fmtPct(m.retorno_anual, 2)}</strong></div>
        <div>Vol: <strong>${fmtPct(m.volatilidade, 2)}</strong></div>
        <div>Inad: <strong>${fmtPct(m.taxa_inad, 2)}</strong></div>
        <div>Hist: <strong>${m.meses_historico}m</strong></div>
      </div>
      <div class="pme-just">${escapeHTML(m.motivo)}</div>
    </div>`;
}

function renderCards() {
  const wrap = byId("match-cards");
  if (!wrap) return;

  if (!state.cpf) { wrap.innerHTML = ""; return; }
  const cliente = Store.clientes.findByCpf(state.cpf);
  if (!cliente) { wrap.innerHTML = ""; return; }

  const top = Store.matches.byCpf(state.cpf)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, TOP_N);

  setHTML("match-cards", `
    ${clientHeaderTpl(cliente)}
    <div class="pme-grid">${top.map(matchCardTpl).join("")}</div>
  `);
}

const tableRowTpl = (m) => `
  <tr>
    <td><span class="rank-badge ${rankBadgeClass(m.rank)}">${m.rank}</span></td>
    <td class="cell-truncate" title="${escapeHTML(m.cliente)}">${escapeHTML(m.cliente)}</td>
    <td><span style="color:${perfilColor(m.perfil_cliente)};font-weight:600;font-size:0.78rem">${escapeHTML(m.perfil_cliente)}</span></td>
    <td class="cell-truncate" title="${escapeHTML(m.fundo)}">${escapeHTML(m.fundo)}</td>
    <td>${escapeHTML(m.tipo_cota)}</td>
    <td><span class="badge ${riscoBadge(m.risco_fundo)}">${escapeHTML(m.risco_fundo)}</span></td>
    <td>${fmtPct(m.retorno_anual, 2)}</td>
    <td><strong>${fmtNum(m.match_score)}</strong></td>
    <td class="cell-truncate" title="${escapeHTML(m.motivo)}">${escapeHTML(m.motivo)}</td>
  </tr>`;

function titleFor(total) {
  const n = total.toLocaleString("pt-BR");
  if (state.cpf)    return `Recomendações do cliente (${n})`;
  if (state.perfil) return `Recomendações do perfil ${state.perfil} (${n})`;
  return `Todas as recomendações (${n})`;
}

const table = createPaginatedTable({
  prefix: "match",
  tbodyId: "tbody-match",
  rowTpl: tableRowTpl,
  colspan: 9,
  empty: "Nenhuma recomendação encontrada",
  noun: "recomendações",
  keyFn: m => `${m.cpf}|${m.fundo}`,
  onUpdate: (page) => setText("match-table-title", titleFor(page.total)),
});

function onStateChange() {
  table.reset();
  renderCards();
  table.render(applyFilters(state));
}

function populateClienteSelect() {
  const sel = byId("f-match-cliente");
  if (!sel) return;
  const options = Store.clientes.lista()
    .slice()
    .sort((a, b) => a.nome.localeCompare(b.nome))
    .map(c => `<option value="${escapeHTML(c.cpf)}">${escapeHTML(c.nome)} (${escapeHTML(c.perfil)})</option>`)
    .join("");
  sel.innerHTML = `<option value="">Selecione um cliente…</option>${options}`;
}

function bindFilters() {
  onChange("f-match-cliente", v => { state.cpf = v; onStateChange(); });
  onChange("f-match-perfil",  v => { state.perfil = v; onStateChange(); });
  onClick("f-match-clear", () => {
    state.cpf = state.perfil = "";
    ["f-match-cliente", "f-match-perfil"].forEach(id => resetField(id));
    onStateChange();
  });
}

export function init() {
  populateClienteSelect();
  table.render(applyFilters(state));
  bindFilters();
}

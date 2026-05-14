import { Store } from "../store.js";
import { fmtInt, fmtNum, fmtDate, escapeHTML } from "../utils/format.js";
import { setText, onInput, onChange } from "../utils/dom.js";
import { memoize } from "../utils/memo.js";
import { perfilColor } from "../theme.js";
import { renderTable } from "../components/table.js";

const EXPERIENCIA = ["Iniciante", "Intermediária", "Avançada"];
const HORIZONTE   = ["< 1 ano", "1–3 anos", "> 3 anos"];

const state = { busca: "", perfil: "" };

const applyFilters = memoize((s) => {
  const buscaLc = s.busca.toLowerCase();
  return Store.clientes.lista().filter(c => {
    if (buscaLc && !c.nome.toLowerCase().includes(buscaLc) && !c.cpf.includes(buscaLc)) return false;
    if (s.perfil && c.perfil !== s.perfil) return false;
    return true;
  });
}, s => `${s.busca}|${s.perfil}`);

const rowTpl = (c) => `
  <tr>
    <td style="font-weight:500">${escapeHTML(c.nome)}</td>
    <td style="font-family:monospace;font-size:0.78rem;color:var(--fg-subtle)">${escapeHTML(c.cpf)}</td>
    <td>${fmtInt(c.idade)}</td>
    <td><span style="color:${perfilColor(c.perfil)};font-weight:700">${escapeHTML(c.perfil)}</span></td>
    <td><strong>${fmtNum(c.score_perfil)}</strong></td>
    <td>${EXPERIENCIA[c.experiencia - 1] ?? "—"}</td>
    <td>${HORIZONTE[c.horizonte - 1] ?? "—"}</td>
    <td style="font-size:0.78rem;color:var(--fg-subtle)">${escapeHTML(fmtDate(c.data_cadastro))}</td>
  </tr>`;

function renderKPIs() {
  const dist = Store.clientes.distribuicao();
  const total = Store.clientes.total() || 1;

  setText("kc-total", fmtInt(Store.clientes.total()));
  setText("kc-cons",  fmtInt(dist.CONSERVADOR ?? 0));
  setText("kc-mod",   fmtInt(dist.MODERADO ?? 0));
  setText("kc-arr",   fmtInt(dist.ARROJADO ?? 0));

  setText("kc-cons-pct", `${(((dist.CONSERVADOR ?? 0) / total) * 100).toFixed(0)}% do total`);
  setText("kc-mod-pct",  `${(((dist.MODERADO    ?? 0) / total) * 100).toFixed(0)}% do total`);
  setText("kc-arr-pct",  `${(((dist.ARROJADO    ?? 0) / total) * 100).toFixed(0)}% do total`);
}

function renderTabela() {
  renderTable("tbody-clientes", applyFilters(state), rowTpl,
    { colspan: 8, empty: "Sem clientes encontrados" });
}

function bindFilters() {
  onInput("f-cli-busca",   v => { state.busca  = v; renderTabela(); });
  onChange("f-cli-perfil", v => { state.perfil = v; renderTabela(); });
}

export function init() {
  renderKPIs();
  renderTabela();
  bindFilters();
}

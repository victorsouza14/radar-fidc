import { Store } from "../store.js";
import { fmtInt, fmtPct, fmtNum, truncate, escapeHTML } from "../utils/format.js";
import { setText } from "../utils/dom.js";
import { riscoColor, riscoBadge, perfilColor } from "../theme.js";
import { doughnut, horizontalBar } from "../components/chart-factory.js";
import { renderTable } from "../components/table.js";

const RISCO_ORDER  = ["BAIXO", "MEDIO", "ALTO"];
const PERFIL_ORDER = ["CONSERVADOR", "MODERADO", "ARROJADO"];

function renderKPIs() {
  const f = Store.fidcs.stats();
  // Conta o mesmo conjunto exibido na aba FIDCs (detalhe paginado) para
  // que o KPI da visão geral case com o total da tabela.
  const analisados = Store.fidcs.detalhe().length;
  setText("kpi-fundos", fmtInt(analisados));
  setText("kpi-classes", `de ${fmtInt(f.total_classes)} classes analisadas`);

  setText("kpi-clientes", fmtInt(Store.clientes.total()));
  const perfis = Store.clientes.distribuicao();
  const desc = Object.entries(perfis)
    .map(([k, v]) => `${v} ${k.toLowerCase()}`)
    .join(" · ") || "—";
  setText("kpi-clientes-perfis", desc);

  const credit = Store.credit.stats();
  setText("kpi-empresas", fmtInt(credit.total));
  const taxa = credit.taxa_default_observada;
  setText("kpi-credit-default",
    taxa != null ? `${(taxa * 100).toFixed(1)}% inadimpliram no histórico` : "—");

  const m = Store.macro();
  setText("kpi-selic", fmtPct(m.selic));
  setText("kpi-cenario", (m.cenario || "—").replace(/_/g, " "));
  setText("footer-date", m.data_ref || "—");
}

// Indicadores macro informativos: exibidos como cards na visão geral
// para substituir a antiga aba "Cenário macroeconômico" (removida).
// Os IDs `*-overview` evitam colisão com IDs históricos preservados em
// outras telas/integrações (mesmo após remoção da seção page-macro).
const PCT2 = (v) => fmtPct(v, 2);

function renderMacroKPIs() {
  const m = Store.macro();
  setText("m-cdi-overview",        fmtPct(m.cdi));
  setText("m-ipca-overview",       PCT2(m.ipca));
  setText("m-selic-proj-overview", fmtPct(m.selic_proj));
  setText("m-ipca-proj-overview",  PCT2(m.ipca_proj));
}

const rankingRow = (r) => `
  <tr>
    <td class="cell-truncate" title="${escapeHTML(r.fundo)}">${escapeHTML(r.fundo)}</td>
    <td>${escapeHTML(r.tipo_cota)}</td>
    <td><span class="badge ${riscoBadge(r.risco)}">${escapeHTML(r.risco)}</span></td>
    <td>${fmtPct(r.retorno_anual)}</td>
    <td><strong>${fmtInt(r.vezes_recomendado)}</strong></td>
    <td>${fmtNum(r.match_medio)}</td>
  </tr>`;

function renderRanking() {
  renderTable("tbody-ranking", Store.matches.rankingFundos(), rankingRow,
    { colspan: 6, empty: "Sem matches disponíveis" });
}

function renderDonuts() {
  const dist = Store.fidcs.stats().distribuicao;

  const risco = dist.por_risco || {};
  const lr = RISCO_ORDER.filter(k => risco[k]);
  const totalR = lr.reduce((a, k) => a + risco[k], 0);
  doughnut("chart-risco", lr, lr.map(k => risco[k]), lr.map(riscoColor), totalR);

  const perfil = dist.por_perfil || {};
  const lp = PERFIL_ORDER.filter(k => perfil[k]);
  const totalP = lp.reduce((a, k) => a + perfil[k], 0);
  doughnut("chart-perfil", lp, lp.map(k => perfil[k]), lp.map(perfilColor), totalP);
}

function selectTop10() {
  // Mesmo threshold do backend para o ranking bater com o de outras telas.
  const minMeses = Store.config().min_meses_historico ?? 6;
  return Store.fidcs.detalhe()
    .filter(f => f.risco !== "SEM DADOS" && f.retorno_anual > 0 && f.meses_historico >= minMeses)
    .sort((a, b) => b.retorno_aj_risco - a.retorno_aj_risco)
    .slice(0, 10);
}

function renderTop10() {
  const top = selectTop10();
  // Truncate em 28 — Chart.js apertaria em viewports estreitos. 28 chars
  // cabe em ~150px @ 11px font, suficiente pro chart no mobile.
  horizontalBar(
    "chart-top10",
    top.map(t => truncate(t.fundo, 28)),
    top.map(t => t.retorno_anual),
    top.map(t => riscoColor(t.risco)),
    ctx => {
      const f = top[ctx.dataIndex];
      return [
        ` Retorno: ${fmtPct(f.retorno_anual, 2)}`,
        ` Risco: ${f.risco} (score ${fmtNum(f.score_risco)})`,
        ` Cota: ${f.tipo_cota} | ${f.meses_historico} meses`,
      ];
    },
  );
}

export function init() {
  renderKPIs();
  renderMacroKPIs();
  renderRanking();
}

export function mount() {
  renderDonuts();
  renderTop10();
}

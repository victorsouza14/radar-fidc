/* Radar FIDC — Trust Bar component.
 *
 * Sticky bar no topo do dashboard que sinaliza saúde da pipeline e
 * frescor dos dados. Decisão do usuário (spec Seção 6):
 *
 *   - 🟢 ok    : pipeline_quality_check.overall_success === true
 *                E nenhuma fonte em data_freshness.* tem status "error"
 *                (freshness "warn" / "stale_expected" continua verde —
 *                evita "amarelo crônico")
 *
 *   - 🔴 error : pipeline_quality_check.overall_success === false
 *                OU alguma fonte em data_freshness.* tem status "error"
 *
 *   - "unknown": manifesto indisponível (fetch falhou). Renderiza
 *                tom neutro com mensagem explícita, não é vermelho
 *                porque pode ser apenas indisponibilidade do JSON em dev.
 *
 * Heurísticas NÃO afetam a cor (markers inline em utils/trust.js).
 *
 * Acessibilidade:
 *   - role="status" + aria-live="polite"  → leitor anuncia mudança
 *   - aria-expanded                       → estado do painel
 *   - aria-controls                       → liga botão ao painel
 *   - ícones aria-hidden                  → texto leva o significado
 *   - Enter/Space toggla painel via teclado
 */

import { loadManifest } from "../utils/trust.js";

const PANEL_ID = "trust-bar-panel";

const STATE_META = {
  ok: {
    icon: "✓",                       // ✓
    label: "Dados confiáveis",
    fullLabel: "Pipeline saudável e dados atualizados",
  },
  error_pipeline: {
    icon: "⛔",                       // ⛔
    label: "Erro na pipeline",
    fullLabel: "Falha de qualidade detectada — verificar runbook",
  },
  error_freshness: {
    icon: "⛔",                       // ⛔
    label: "Dados desatualizados",
    fullLabel: "Fonte de dados além do threshold — pipeline ETL pode estar travada",
  },
  unknown: {
    icon: "ℹ",                       // ℹ
    label: "Status indisponível",
    fullLabel: "Manifesto de qualidade não pôde ser carregado",
  },
};
// Alias de compatibilidade — código legado e CSS data-state usam "error".
STATE_META.error = STATE_META.error_pipeline;

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

/**
 * Decide o estado do trust bar a partir do manifesto.
 *
 * @param {object|null} manifest
 * @returns {"ok"|"error"|"unknown"}
 */
function pickState(manifest) {
  if (!manifest) return "unknown";

  const pq = manifest.pipeline_quality_check || {};
  const freshness = manifest.data_freshness || {};

  const pipelineFailed = pq.overall_success === false;
  const sourceFailed = Object.values(freshness).some(
    (entry) => entry && entry.status === "error"
  );

  if (pipelineFailed) return "error_pipeline";
  if (sourceFailed) return "error_freshness";

  // overall_success === true OU não declarado, e nenhum source com erro.
  return "ok";
}

/**
 * Resumo curto exibido inline à direita no header do bar.
 *
 * @param {object|null} manifest
 * @returns {string}
 */
function summaryLine(manifest) {
  if (!manifest) return "";

  const parts = [];

  const ts = manifest.generated_at;
  if (typeof ts === "string" && ts.length > 0) {
    parts.push(`Atualizado: ${formatTimestamp(ts)}`);
  }

  // Detalhamento de heurísticas fica no painel expandido (clique no caret),
  // não no resumo inline. Mantém o header limpo.
  return parts.join(" · ");                 // " · "
}

/**
 * Formata ISO timestamp como "DD/MM HH:mm" pt-BR.
 * Retorna o valor original se parsing falhar.
 *
 * @param {string} iso
 * @returns {string}
 */
function formatTimestamp(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm} ${hh}:${mi}`;
}

/**
 * Renderiza o painel expandido com detalhes do manifesto.
 *
 * @param {object|null} manifest
 * @returns {string}
 */
function renderPanelContent(manifest) {
  if (!manifest) {
    return `
      <p class="trust-bar__panel-title">Detalhes</p>
      <p class="fetch-error__message">
        Não foi possível carregar <code>data-quality.json</code>.
        Verifique se o pipeline gerou o manifesto recentemente.
      </p>
    `;
  }

  const generatedAt = manifest.generated_at
    ? `<div class="trust-bar__panel-item">
         <span class="trust-bar__panel-item-label">Gerado em</span>
         <span class="trust-bar__panel-item-value">${escapeHTML(manifest.generated_at)}</span>
       </div>`
    : "";

  const pq = manifest.pipeline_quality_check || {};
  const pipelineStatus = pq.overall_success === true
    ? "OK"
    : pq.overall_success === false
      ? "Falhou"
      : "N/A";
  const pipelineStatusAttr = pq.overall_success === true
    ? "fresh"
    : pq.overall_success === false
      ? "error"
      : "";

  const pipelineRun = pq.run_id
    ? `<div class="trust-bar__panel-item">
         <span class="trust-bar__panel-item-label">Última pipeline</span>
         <span class="trust-bar__panel-item-value" data-status="${escapeHTML(pipelineStatusAttr)}">${escapeHTML(pipelineStatus)} · ${escapeHTML(pq.run_id)}</span>
       </div>`
    : `<div class="trust-bar__panel-item">
         <span class="trust-bar__panel-item-label">Última pipeline</span>
         <span class="trust-bar__panel-item-value" data-status="${escapeHTML(pipelineStatusAttr)}">${escapeHTML(pipelineStatus)}</span>
       </div>`;

  const freshness = manifest.data_freshness || {};
  const freshnessItems = Object.entries(freshness)
    .map(([source, info]) => {
      const status = info && info.status ? String(info.status) : "unknown";
      const ref = info && info.data_ref ? String(info.data_ref) : "—";
      return `<div class="trust-bar__panel-item">
        <span class="trust-bar__panel-item-label">${escapeHTML(source)}</span>
        <span class="trust-bar__panel-item-value" data-status="${escapeHTML(status)}">${escapeHTML(ref)} (${escapeHTML(status)})</span>
      </div>`;
    })
    .join("");

  const heuristicsCount = Array.isArray(manifest.heuristic_fields)
    ? manifest.heuristic_fields.length
    : 0;
  const heuristicsItem = heuristicsCount > 0
    ? `<div class="trust-bar__panel-item">
         <span class="trust-bar__panel-item-label">Heurísticas ativas</span>
         <span class="trust-bar__panel-item-value" data-status="warn">${heuristicsCount} campo${heuristicsCount === 1 ? "" : "s"}</span>
       </div>`
    : "";

  return `
    <p class="trust-bar__panel-title">Detalhes do manifesto</p>
    <div class="trust-bar__panel-grid">
      ${generatedAt}
      ${pipelineRun}
      ${freshnessItems}
      ${heuristicsItem}
    </div>
    <p class="trust-bar__panel-footer">
      Pipeline e fontes documentadas em
      <a href="docs/operacao.md">docs/operacao.md</a>.
    </p>
  `;
}

/**
 * Monta e injeta o trust bar no topo do root informado.
 *
 * @param {string} rootSelector  default: "body"
 * @returns {Promise<HTMLElement|null>}
 */
export async function renderTrustBar(rootSelector = "body") {
  const root = document.querySelector(rootSelector);
  if (!root) return null;

  const manifest = await loadManifest();
  const state = pickState(manifest);
  const meta = STATE_META[state];
  const summary = summaryLine(manifest);

  const bar = document.createElement("div");
  bar.className = "trust-bar";
  bar.setAttribute("role", "status");
  bar.setAttribute("aria-live", "polite");
  bar.setAttribute("aria-atomic", "true");
  bar.setAttribute("aria-expanded", "false");
  bar.setAttribute("aria-controls", PANEL_ID);
  bar.setAttribute("tabindex", "0");
  // CSS only knows ok|error|unknown — map the two error sub-states to "error"
  // but expose the precise variant via data-state-detail for diagnostics/tooling.
  const cssState = state.startsWith("error") ? "error" : state;
  bar.setAttribute("data-state", cssState);
  bar.setAttribute("data-state-detail", state);
  bar.setAttribute("data-trust-bar", "true");

  bar.innerHTML = `
    <span class="trust-bar__icon" aria-hidden="true">${escapeHTML(meta.icon)}</span>
    <span class="trust-bar__label">${escapeHTML(meta.label)}</span>
    <span class="trust-bar__details" aria-hidden="${summary ? "false" : "true"}">${escapeHTML(summary)}</span>
    <span class="trust-bar__caret" aria-hidden="true">▼</span>
  `;

  // Painel expandível com detalhes — fica como sibling para evitar
  // problemas de clipping/sticky scope no bar.
  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.className = "trust-bar__panel";
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-label", "Detalhes do status de qualidade dos dados");
  panel.hidden = true;
  panel.innerHTML = renderPanelContent(manifest);

  const togglePanel = () => {
    const expanded = bar.getAttribute("aria-expanded") === "true";
    bar.setAttribute("aria-expanded", expanded ? "false" : "true");
    panel.hidden = expanded;
  };

  bar.addEventListener("click", togglePanel);
  bar.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      togglePanel();
    } else if (event.key === "Escape") {
      bar.setAttribute("aria-expanded", "false");
      panel.hidden = true;
    }
  });

  // Fecha o painel quando clica fora.
  document.addEventListener("click", (event) => {
    if (panel.hidden) return;
    const target = event.target;
    if (target instanceof Node && !bar.contains(target) && !panel.contains(target)) {
      bar.setAttribute("aria-expanded", "false");
      panel.hidden = true;
    }
  });

  // Insere no topo do root, antes do primeiro filho.
  root.insertBefore(panel, root.firstChild);
  root.insertBefore(bar, root.firstChild);

  // Anuncia para leitores de tela a mensagem completa.
  bar.setAttribute("aria-label", `${meta.fullLabel}. Clique para detalhes.`);

  return bar;
}

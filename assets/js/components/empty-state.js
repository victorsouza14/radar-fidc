/* Radar FIDC — Empty State component.
 *
 * Bloco reutilizável para "sem dados" / "filtro vazio" / "selecione algo".
 * Retorna HTML como string para injeção via innerHTML.
 *
 * Uso:
 *   import { renderEmptyState } from "../components/empty-state.js";
 *
 *   container.innerHTML = renderEmptyState({
 *     title: "Sem matches",
 *     description: "Nenhum FIDC compatível com este perfil + filtros.",
 *     suggestions: [
 *       "Revisar segmento da PME",
 *       "Considerar qualificação como investidor",
 *     ],
 *   });
 *
 * Acessibilidade:
 *   - role="status" para anúncio por leitor de tela
 *   - aria-live="polite" (não interrompe)
 *   - ícone com aria-hidden — texto carrega o significado
 */

const DEFAULT_ICON = "🔍";

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
 * Renderiza empty state como string HTML.
 *
 * @param {object} options
 * @param {string} options.title         título principal (obrigatório)
 * @param {string} [options.description] descrição (opcional)
 * @param {string[]} [options.suggestions] lista de sugestões (opcional)
 * @param {string} [options.icon]        emoji/ícone (default 🔍)
 * @returns {string} HTML seguro (escapado)
 */
export function renderEmptyState({
  title,
  description = "",
  suggestions = [],
  icon = DEFAULT_ICON,
} = {}) {
  const safeTitle = escapeHTML(title || "Sem dados");
  const safeIcon = escapeHTML(icon);

  const descBlock = description
    ? `<p class="empty-state__desc">${escapeHTML(description)}</p>`
    : "";

  const suggestionsList = Array.isArray(suggestions) && suggestions.length > 0
    ? `<ul class="empty-state__suggestions">
         ${suggestions.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}
       </ul>`
    : "";

  return `
    <div class="empty-state" role="status" aria-live="polite" data-empty-state="true">
      <span class="empty-state__icon" aria-hidden="true">${safeIcon}</span>
      <h3 class="empty-state__title">${safeTitle}</h3>
      ${descBlock}
      ${suggestionsList}
    </div>
  `;
}

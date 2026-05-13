// Renderer de tabela genérico. Recebe rows + rowTemplate e cuida do batched write
// + estado vazio. Evita N reflows em loops innerHTML+=.

const DEFAULT_EMPTY = "Nenhum registro encontrado";

/**
 * Renderiza linhas em um <tbody>.
 *
 * @param {string} tbodyId       — id do tbody
 * @param {Array}  rows          — array de objetos
 * @param {(row, i) => string} rowTemplate — template HTML para cada linha
 * @param {object} [options]
 * @param {number} [options.limit]      — limite de linhas exibidas
 * @param {number} [options.colspan]    — colspan da row de empty state
 * @param {string} [options.empty]      — mensagem de empty state
 */
export function renderTable(tbodyId, rows, rowTemplate, options = {}) {
  const { limit = 200, colspan = 1, empty = DEFAULT_EMPTY } = options;
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;

  if (!rows.length) {
    tbody.innerHTML =
      `<tr><td colspan="${colspan}" style="text-align:center;padding:32px;color:var(--ink-500)">${empty}</td></tr>`;
    return;
  }

  const slice = rows.slice(0, limit);
  // Build com array.join (rápido) → 1 atribuição DOM.
  tbody.innerHTML = slice.map(rowTemplate).join("");
}

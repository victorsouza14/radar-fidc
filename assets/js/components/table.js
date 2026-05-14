const DEFAULT_EMPTY = "Nenhum registro encontrado";

export function renderTable(tbodyId, rows, rowTemplate, options = {}) {
  const { limit = 200, colspan = 1, empty = DEFAULT_EMPTY } = options;
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;

  if (!rows.length) {
    tbody.innerHTML =
      `<tr><td colspan="${colspan}" style="text-align:center;padding:32px;color:var(--fg-subtle)">${empty}</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.slice(0, limit).map(rowTemplate).join("");
}

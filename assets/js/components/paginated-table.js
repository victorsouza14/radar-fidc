import { byId, setText, onClick } from "../utils/dom.js";
import { paginate } from "../utils/pagination.js";

/**
 * Cria controlador de tabela paginada com cursor (REST-style).
 *
 * O DOM precisa ter, sob um prefixo comum, os elementos:
 *   - <tbody id="{tbodyId}">
 *   - <div   id="{prefix}-pagination">                (wrapper)
 *   - <div   id="{prefix}-pagination-info">
 *   - <span  id="{prefix}-pagination-page">
 *   - <button id="{prefix}-pagination-prev">
 *   - <button id="{prefix}-pagination-next">
 *
 * Uso:
 *   const table = createPaginatedTable({ ... });
 *   table.render(filteredList);   // recalcula a 1ª página
 *   table.reset();                // limpa cursor (chamar quando filtros mudam)
 */
export function createPaginatedTable({
  prefix,
  tbodyId,
  rowTpl,
  colspan,
  empty,
  noun,
  pageSize = 50,
  keyField = "id",
  keyFn = null,
  onUpdate = () => {},
}) {
  const ids = {
    wrap: `${prefix}-pagination`,
    info: `${prefix}-pagination-info`,
    page: `${prefix}-pagination-page`,
    prev: `${prefix}-pagination-prev`,
    next: `${prefix}-pagination-next`,
  };
  const FILLER = `<tr class="filler-row" aria-hidden="true"><td colspan="${colspan}">&nbsp;</td></tr>`;

  let cursor = null;
  let list = [];

  const compute = () => paginate(list, { cursor, pageSize, keyField, keyFn });

  function renderRows(page) {
    const tbody = byId(tbodyId);
    if (!tbody) return;
    if (page.total === 0) {
      tbody.innerHTML =
        `<tr><td colspan="${colspan}" style="text-align:center;padding:32px;color:var(--fg-subtle)">${empty}</td></tr>`;
      return;
    }
    const rows    = page.items.map(rowTpl).join("");
    const fillers = FILLER.repeat(Math.max(0, pageSize - page.items.length));
    tbody.innerHTML = rows + fillers;
  }

  function renderControls(page) {
    const wrap = byId(ids.wrap);
    if (!wrap) return;
    if (page.total <= pageSize) { wrap.hidden = true; return; }
    wrap.hidden = false;

    const totalPages  = Math.max(1, Math.ceil(page.total / pageSize));
    const currentPage = Math.floor((page.pageStart - 1) / pageSize) + 1;

    setText(ids.info, `Mostrando ${page.pageStart}–${page.pageEnd} de ${page.total.toLocaleString("pt-BR")} ${noun}`);
    setText(ids.page, `Página ${currentPage} de ${totalPages}`);
    byId(ids.prev).disabled = !page.hasPrev;
    byId(ids.next).disabled = !page.hasNext;
  }

  function update() {
    const page = compute();
    renderRows(page);
    renderControls(page);
    onUpdate(page);
    return page;
  }

  function next() {
    const page = compute();
    if (!page.hasNext) return;
    cursor = page.nextCursor;
    update();
  }

  function prev() {
    const page = compute();
    if (!page.hasPrev) return;
    cursor = page.prevCursor;
    update();
  }

  onClick(ids.prev, prev);
  onClick(ids.next, next);

  return {
    render(items) { list = items; return update(); },
    reset() { cursor = null; },
  };
}

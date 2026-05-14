/**
 * Keyset/cursor pagination — segue o padrão recomendado por REST APIs
 * de produção (Merge.dev, Stripe, GitHub): cursor opaco baseado em chave
 * estável do item, em vez de offset numérico.
 *
 * Diferenças vs offset/page:
 *   - Não sofre "page drift" quando o conjunto muda (filtros, inserts).
 *   - Cursor é stateless: cliente só guarda nextCursor/prevCursor.
 *   - hasNext/hasPrev derivados do payload, não calculados pelo cliente.
 *
 * @param {Array}  items     — lista ordenada e estável.
 * @param {Object} opts
 * @param {string|null} opts.cursor   — chave do 1º item da página (string).
 * @param {number} opts.pageSize     — itens por página (default 50).
 * @param {string} [opts.keyField]   — propriedade única no item (usado se keyFn não passado).
 * @param {(item) => string} [opts.keyFn] — derivador de chave (composto p/ ex.).
 *
 * @returns {{
 *   items: Array, total: number, pageStart: number, pageEnd: number,
 *   nextCursor: string|null, prevCursor: string|null,
 *   hasNext: boolean, hasPrev: boolean
 * }}
 */
export function paginate(items, { cursor = null, pageSize = 50, keyField = "id", keyFn = null } = {}) {
  const total = items.length;
  const getKey = keyFn ?? ((it) => it[keyField]);

  // Cursor null/inexistente → primeira página (zero-state).
  let start = 0;
  if (cursor != null) {
    const idx = items.findIndex(it => getKey(it) === cursor);
    if (idx >= 0) start = idx;
  }
  const end = Math.min(start + pageSize, total);

  const nextStart = end;
  const prevStart = Math.max(0, start - pageSize);

  return {
    items:      items.slice(start, end),
    total,
    pageStart:  total === 0 ? 0 : start + 1,
    pageEnd:    end,
    nextCursor: nextStart < total ? getKey(items[nextStart]) : null,
    prevCursor: start > 0          ? getKey(items[prevStart]) : null,
    hasNext:    nextStart < total,
    hasPrev:    start > 0,
  };
}

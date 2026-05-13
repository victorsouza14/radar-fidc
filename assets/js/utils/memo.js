// Memoization simples para filtros — cacheia o último resultado se a key não mudou.
// Útil para evitar re-filtrar 1500 itens enquanto o usuário só interage com a UI.

/**
 * Cria uma versão memoizada de fn(state) -> result.
 * `keyFn(state)` deve retornar uma string que identifique a "versão" do estado.
 */
export function memoize(fn, keyFn) {
  let lastKey = null;
  let lastResult = null;
  return (state) => {
    const k = keyFn(state);
    if (k === lastKey) return lastResult;
    lastKey = k;
    lastResult = fn(state);
    return lastResult;
  };
}

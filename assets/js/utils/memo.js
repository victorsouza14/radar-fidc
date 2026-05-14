/**
 * Cacheia o último resultado de fn(state) enquanto keyFn(state) não mudar.
 * Usado em pipelines de filtro para evitar recomputar listas longas.
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

// Helpers DOM compartilhados. Cache de refs + listeners com debounce nativo.

/** Cache de referências por id — evita getElementById repetido. */
const _refCache = new Map();
export function byId(id) {
  let el = _refCache.get(id);
  if (el && el.isConnected) return el;
  el = document.getElementById(id);
  if (el) _refCache.set(id, el);
  return el;
}

/** Atribui textContent só se o elemento existir (e mudou). */
export function setText(idOrEl, text) {
  const el = typeof idOrEl === "string" ? byId(idOrEl) : idOrEl;
  if (el && el.textContent !== text) el.textContent = text;
}

/** Atribui innerHTML em batch e retorna o elemento. */
export function setHTML(idOrEl, html) {
  const el = typeof idOrEl === "string" ? byId(idOrEl) : idOrEl;
  if (el) el.innerHTML = html;
  return el;
}

/** Debounce simples — ideal para inputs. */
export function debounce(fn, wait = 200) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

/** Liga input com debounce. Retorna função de unbind. */
export function onInput(id, handler, wait = 250) {
  const el = byId(id);
  if (!el) return () => {};
  const h = debounce(e => handler(e.target.value.trim()), wait);
  el.addEventListener("input", h);
  return () => el.removeEventListener("input", h);
}

/** Liga change (sem debounce). */
export function onChange(id, handler) {
  const el = byId(id);
  if (!el) return () => {};
  const h = e => handler(e.target.value);
  el.addEventListener("change", h);
  return () => el.removeEventListener("change", h);
}

/** Liga click. */
export function onClick(id, handler) {
  const el = byId(id);
  if (!el) return () => {};
  el.addEventListener("click", handler);
  return () => el.removeEventListener("click", handler);
}

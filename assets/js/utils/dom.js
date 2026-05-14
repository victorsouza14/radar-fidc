const _refCache = new Map();

export function byId(id) {
  let el = _refCache.get(id);
  if (el && el.isConnected) return el;
  el = document.getElementById(id);
  if (el) _refCache.set(id, el);
  return el;
}

export function setText(idOrEl, text) {
  const el = typeof idOrEl === "string" ? byId(idOrEl) : idOrEl;
  if (el && el.textContent !== text) el.textContent = text;
}

export function setHTML(idOrEl, html) {
  const el = typeof idOrEl === "string" ? byId(idOrEl) : idOrEl;
  if (el) el.innerHTML = html;
  return el;
}

export function debounce(fn, wait = 200) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

export function onInput(id, handler, wait = 250) {
  const el = byId(id);
  if (!el) return () => {};
  const h = debounce(e => handler(e.target.value.trim()), wait);
  el.addEventListener("input", h);
  return () => el.removeEventListener("input", h);
}

export function onChange(id, handler) {
  const el = byId(id);
  if (!el) return () => {};
  const h = e => handler(e.target.value);
  el.addEventListener("change", h);
  return () => el.removeEventListener("change", h);
}

export function onClick(id, handler) {
  const el = byId(id);
  if (!el) return () => {};
  el.addEventListener("click", handler);
  return () => el.removeEventListener("click", handler);
}

/**
 * Reseta value e emite `radar:sync` para custom selects atualizarem o label
 * (não usa `change` porque dispararia handlers de filtro da página de novo).
 */
export function resetField(id, value = "") {
  const el = byId(id);
  if (!el) return;
  el.value = value;
  el.dispatchEvent(new Event("radar:sync"));
}

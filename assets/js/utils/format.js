const PLACEHOLDER = "—";

const isNullish = (v) => v == null || (typeof v === "number" && Number.isNaN(v));
const toNumber  = (v) => (typeof v === "number" ? v : Number(v));

export function fmtPct(value, digits = 1) {
  if (isNullish(value)) return PLACEHOLDER;
  const n = toNumber(value);
  return Number.isNaN(n) ? PLACEHOLDER : `${n.toFixed(digits)}%`;
}

export function fmtNum(value, digits = 1) {
  if (isNullish(value)) return PLACEHOLDER;
  const n = toNumber(value);
  return Number.isNaN(n) ? PLACEHOLDER : n.toFixed(digits);
}

export function fmtInt(value) {
  if (isNullish(value)) return PLACEHOLDER;
  const n = toNumber(value);
  return Number.isNaN(n) ? PLACEHOLDER : Math.round(n).toLocaleString("pt-BR");
}

export function truncate(text, max = 40, suffix = "…") {
  if (!text) return "";
  const s = String(text);
  return s.length > max ? s.slice(0, max) + suffix : s;
}

const HTML_ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export function escapeHTML(value) {
  if (value == null) return "";
  return String(value).replace(/[&<>"']/g, ch => HTML_ESC[ch]);
}

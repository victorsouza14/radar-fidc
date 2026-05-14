/* Radar FIDC — trust manifest consumer.
 *
 * Consome `data-quality.json` (gerado pelo pipeline Python) e expõe
 * utilidades para o frontend:
 *
 *   - loadManifest()       → Promise<Manifest|null>  (cache em memória)
 *   - markHeuristic(key)   → Promise<string>          (HTML escapado)
 *   - isHeuristic(key)     → Promise<boolean>
 *
 * Quando a Fase 3 esvaziar `heuristic_fields`, os markers somem
 * automaticamente sem mudança de código nas pages.
 *
 * Falha de fetch é silenciosa por design: o trust bar e markers nunca
 * podem quebrar o app. Em caso de falha, `markHeuristic` retorna string
 * vazia e o trust bar renderiza estado "unknown".
 */

const MANIFEST_URL = "data-quality.json";

let _manifestPromise = null;

/**
 * Escapa caracteres especiais HTML para prevenir XSS em atributos
 * (title/aria-label) e em valores injetados via innerHTML.
 *
 * @param {unknown} value
 * @returns {string}
 */
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
 * Carrega o manifesto uma única vez por sessão (cache em memória).
 * Falha silenciosamente: retorna `null` se o JSON não existir ou
 * estiver corrompido. O trust bar trata `null` como estado "unknown".
 *
 * @returns {Promise<object|null>}
 */
export function loadManifest() {
  if (_manifestPromise) return _manifestPromise;

  _manifestPromise = fetch(`${MANIFEST_URL}?v=${Date.now()}`, { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .catch(() => null);

  return _manifestPromise;
}

/**
 * Reseta o cache (útil para testes e para forçar reload).
 */
export function resetManifestCache() {
  _manifestPromise = null;
}

/**
 * Retorna `true` se o campo está no array `heuristic_fields` do manifesto.
 *
 * @param {string} fieldKey  ex: "macro.selic_proj"
 * @returns {Promise<boolean>}
 */
export async function isHeuristic(fieldKey) {
  const manifest = await loadManifest();
  if (!manifest || !Array.isArray(manifest.heuristic_fields)) return false;
  return manifest.heuristic_fields.some((entry) => entry && entry.field === fieldKey);
}

/**
 * Encontra a entrada de heurística para o campo (ou null).
 *
 * @param {string} fieldKey
 * @returns {Promise<{field: string, method?: string, since?: string}|null>}
 */
async function findEntry(fieldKey) {
  const manifest = await loadManifest();
  if (!manifest || !Array.isArray(manifest.heuristic_fields)) return null;
  return manifest.heuristic_fields.find((entry) => entry && entry.field === fieldKey) ?? null;
}

/**
 * Retorna um snippet HTML seguro para ser injetado via innerHTML ao
 * lado de um valor heurístico. Quando o campo NÃO é heurístico (ou
 * manifesto indisponível), retorna string vazia — o que faz o marker
 * desaparecer automaticamente quando a heurística é substituída por
 * dado real.
 *
 * O snippet inclui:
 *   - role="img" + aria-label  → leitor de tela anuncia "heurística..."
 *   - title                    → tooltip nativo do navegador
 *   - ícone ⚠ aria-hidden      → cor não é o único sinal
 *   - texto "heurística"       → visível inclusive em alto contraste
 *
 * @param {string} fieldKey  ex: "macro.selic_proj"
 * @returns {Promise<string>}
 */
export async function markHeuristic(fieldKey) {
  const entry = await findEntry(fieldKey);
  if (!entry) return "";

  const method = entry.method ? `: ${entry.method}` : "";
  const since = entry.since ? ` (desde ${entry.since})` : "";
  const tooltip = `Heurística${method}${since}. Será substituída por fonte oficial em fase posterior.`;
  const safeTooltip = escapeHTML(tooltip);

  return `<span class="heuristic-marker" role="img" aria-label="${safeTooltip}" title="${safeTooltip}" tabindex="0">` +
    `<span class="heuristic-marker__icon" aria-hidden="true">&#9888;</span>` +
    `<span>heurística</span>` +
    `</span>`;
}

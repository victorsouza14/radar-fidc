/* Radar FIDC — Fetch Error component + data caching.
 *
 * Fallback gracioso quando o fetch de `data.json` falha. Mostra:
 *   - mensagem de erro com aria-live (anunciada por leitor de tela)
 *   - informação sobre cópia em cache (se disponível)
 *   - botão "Recarregar"
 *
 * Também expõe `cacheData()` / `getCachedData()` para o store
 * persistir/restaurar o último payload bem-sucedido em localStorage.
 *
 * A chave usa namespace para não colidir com outros apps no mesmo origin.
 */

export const STORAGE_KEY = "radar-fidc:last-known-data";
export const STORAGE_KEY_TIMESTAMP = "radar-fidc:last-known-data:ts";

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
 * Persiste o último data.json bem-sucedido em localStorage.
 * Falha silenciosa: quota cheia, private mode, storage desabilitado
 * → o app continua funcionando sem cache.
 *
 * @param {unknown} data
 */
export function cacheData(data) {
  if (data == null) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    localStorage.setItem(STORAGE_KEY_TIMESTAMP, new Date().toISOString());
  } catch (_err) {
    /* storage indisponível — degrada silenciosamente. */
  }
}

/**
 * Restaura o último payload conhecido, ou null se nunca houve sucesso.
 *
 * @returns {{data: unknown, timestamp: string|null}|null}
 */
export function getCachedData() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    const timestamp = localStorage.getItem(STORAGE_KEY_TIMESTAMP);
    return { data, timestamp };
  } catch (_err) {
    return null;
  }
}

/**
 * Limpa o cache (útil para testes manuais).
 */
export function clearCachedData() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_KEY_TIMESTAMP);
  } catch (_err) {
    /* nada a fazer. */
  }
}

function formatTimestamp(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm}/${yy} ${hh}:${mi}`;
}

/**
 * Renderiza o banner de erro de fetch.
 *
 * @param {object} options
 * @param {string} [options.message]   mensagem técnica (default: "erro desconhecido")
 * @param {Function} [options.onRetry] callback do botão Recarregar (default: location.reload)
 * @returns {HTMLElement}
 */
export function renderFetchError({ message = "erro desconhecido", onRetry } = {}) {
  const banner = document.createElement("div");
  banner.className = "fetch-error";
  banner.setAttribute("role", "alert");
  banner.setAttribute("aria-live", "assertive");
  banner.setAttribute("data-fetch-error", "true");

  const cached = getCachedData();
  const cacheInfo = cached && cached.timestamp
    ? `<p class="fetch-error__cache-info">Última cópia conhecida: ${escapeHTML(formatTimestamp(cached.timestamp))}.</p>`
    : `<p class="fetch-error__cache-info">Nenhuma cópia em cache disponível.</p>`;

  banner.innerHTML = `
    <div class="fetch-error__header">
      <span class="fetch-error__icon" aria-hidden="true">&#9888;</span>
      <span>Não foi possível carregar os dados</span>
    </div>
    <p class="fetch-error__message">${escapeHTML(message)}</p>
    ${cacheInfo}
    <div class="fetch-error__actions">
      <button type="button" class="fetch-error__action" data-action="retry">Recarregar</button>
    </div>
  `;

  const retryBtn = banner.querySelector('[data-action="retry"]');
  if (retryBtn) {
    retryBtn.addEventListener("click", () => {
      if (typeof onRetry === "function") {
        onRetry();
      } else {
        window.location.reload();
      }
    });
  }

  return banner;
}

/* Radar FIDC — trust manifest consumer.
 *
 * Consome `data-quality.json` (gerado pelo pipeline Python) e expõe
 * utilidades para o frontend:
 *
 *   - loadManifest()       → Promise<Manifest|null>  (cache em memória)
 *   - resetManifestCache() → void
 *
 * Falha de fetch é silenciosa por design: o trust bar nunca pode quebrar
 * o app. Em caso de falha, retorna `null` e o trust bar renderiza estado
 * "unknown".
 */

const MANIFEST_URL = "data-quality.json";

let _manifestPromise = null;

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


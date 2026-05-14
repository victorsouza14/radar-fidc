import { load } from "./store.js";
import * as router from "./router.js";
import { bootUI } from "./ui.js";
import { enhanceAllSelects } from "./components/select.js";
import { renderFetchError } from "./components/fetch-error.js";

import * as overview from "./pages/overview.js";
import * as fidcs    from "./pages/fidcs.js";
import * as match    from "./pages/match.js";
import * as credit   from "./pages/credit.js";

function showError(message) {
  document.querySelectorAll(".kpi-value").forEach(el => { el.textContent = "—"; });
  const main = document.getElementById("main");
  if (!main) return;
  const banner = renderFetchError({
    message,
    onRetry: () => window.location.reload(),
  });
  main.prepend(banner);
}

async function boot() {
  bootUI();

  try {
    await load();
  } catch (e) {
    console.error("[Radar] load falhou:", e);
    showError(e.message);
    return;
  }

  router.register("overview", { init: overview.init, mount: overview.mount });
  router.register("fidcs",    { init: fidcs.init,    mount: fidcs.mount });
  router.register("match",    { init: match.init });
  router.register("credit",   { init: credit.init,   mount: credit.mount });

  router.bootstrap("overview");
  enhanceAllSelects();
}

boot();

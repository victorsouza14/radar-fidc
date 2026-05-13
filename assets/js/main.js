// Entry point — orquestra load do store e registra páginas no router.

import { load } from "./store.js";
import * as router from "./router.js";

import * as overview from "./pages/overview.js";
import * as fidcs    from "./pages/fidcs.js";
import * as macro    from "./pages/macro.js";
import * as clientes from "./pages/clientes.js";
import * as match    from "./pages/match.js";
import * as credit   from "./pages/credit.js";

function showError(message) {
  document.querySelectorAll(".kpi-value").forEach(el => { el.textContent = "—"; });
  const main = document.querySelector("main");
  if (!main) return;
  const banner = document.createElement("div");
  banner.className = "error-banner";
  banner.innerHTML =
    `<strong>Falha ao carregar dados:</strong> ${message}<br>` +
    `Verifique se <code>data.json</code> existe na raiz e foi gerado pelo pipeline.`;
  main.prepend(banner);
}

async function boot() {
  try {
    await load();
  } catch (e) {
    console.error("[Radar] load falhou:", e);
    showError(e.message);
    return;
  }

  router.register("overview", { init: overview.init, mount: overview.mount });
  router.register("fidcs",    { init: fidcs.init,    mount: fidcs.mount });
  router.register("macro",    { init: macro.init,    mount: macro.mount });
  router.register("clientes", { init: clientes.init });
  router.register("match",    { init: match.init });
  router.register("credit",   { init: credit.init,   mount: credit.mount });

  router.bootstrap("overview");
}

boot();

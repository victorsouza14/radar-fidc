const handlers = new Map();
const _inited  = new Set();
const _mounted = new Set();

const PAGE_TITLES = {
  overview: "Visão geral",
  fidcs:    "FIDCs",
  macro:    "Cenário macroeconômico",
  clientes: "Clientes",
  match:    "Recomendações",
  credit:   "Credit scoring",
};

export function register(pageId, page) {
  if (typeof page === "function") {
    handlers.set(pageId, { init: page, mount: () => {} });
  } else {
    handlers.set(pageId, { init: page.init ?? (() => {}), mount: page.mount ?? (() => {}) });
  }
}

function activate(pageId) {
  document.querySelectorAll(".page").forEach(p => {
    p.classList.toggle("active", p.id === "page-" + pageId);
  });
}

function syncNav(btn) {
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
}

function syncBreadcrumb(pageId) {
  const el = document.getElementById("breadcrumb-current");
  if (el && PAGE_TITLES[pageId]) el.textContent = PAGE_TITLES[pageId];
}

function maybeCloseMobileDrawer() {
  if (!window.matchMedia("(max-width: 768px)").matches) return;
  document.getElementById("app")?.removeAttribute("data-sidebar");
}

function ensureInited(pageId) {
  if (_inited.has(pageId)) return;
  const h = handlers.get(pageId);
  if (!h) return;
  h.init();
  _inited.add(pageId);
}

function ensureMounted(pageId) {
  if (_mounted.has(pageId)) return;
  const h = handlers.get(pageId);
  if (!h) return;
  ensureInited(pageId);

  // Chart.js mede via container; páginas inativas estão em display:none → width=0.
  // .measuring posiciona off-screen mantendo width real para a medição funcionar.
  const sec = document.getElementById("page-" + pageId);
  const wasActive = sec?.classList.contains("active");
  if (sec && !wasActive) sec.classList.add("measuring");

  try {
    h.mount();
  } finally {
    if (sec && !wasActive) sec.classList.remove("measuring");
  }
  _mounted.add(pageId);
}

export function remountAll() {
  _mounted.clear();
  const active = document.querySelector(".page.active");
  if (!active) return;
  const pageId = active.id.replace(/^page-/, "");
  requestAnimationFrame(() => ensureMounted(pageId));
}

export function go(pageId, btn) {
  activate(pageId);
  syncNav(btn);
  syncBreadcrumb(pageId);
  maybeCloseMobileDrawer();
  requestAnimationFrame(() => ensureMounted(pageId));
}

export function bootstrap(initialPageId) {
  for (const id of handlers.keys()) ensureInited(id);
  requestAnimationFrame(() => ensureMounted(initialPageId));

  const sidebar = document.querySelector(".sidebar");
  if (sidebar) {
    sidebar.addEventListener("click", (ev) => {
      const trigger = ev.target.closest("[data-page]");
      if (!trigger) return;
      const pageId = trigger.dataset.page;
      const navBtn = document.querySelector(`.nav-btn[data-page="${pageId}"]`);
      go(pageId, navBtn || trigger);
    });
  }
}

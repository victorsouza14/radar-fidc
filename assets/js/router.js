// Router — boot eager para KPIs/tabelas, lazy mount para charts.
//
// Cada página registra { init, mount }:
//   - init(): tabelas, KPIs, binds — barato, roda no boot para todas
//   - mount(): charts — caro, roda 1x na 1ª ativação (canvas precisa estar visível)
//
// Ao trocar de aba já visitada: NADA é re-renderizado. Sem flash, sem flicker.
//
// Navegação: usa delegação de eventos via `data-page` nos botões (CSP-friendly).

const handlers = new Map();   // pageId -> { init, mount }
const _inited  = new Set();
const _mounted = new Set();

export function register(pageId, page) {
  // page pode ser { init, mount } ou só uma função (compat)
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

  // Chart.js mede o canvas pelo seu container. Páginas inativas estão em
  // display:none — width=0 → chart fica vazio. A classe `.measuring` (em layout.css)
  // posiciona a página off-screen com largura real para Chart.js medir.
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

export function go(pageId, btn) {
  activate(pageId);
  syncNav(btn);
  // Mount lazy: roda só na 1ª ativação (canvas agora tem tamanho real).
  // Em rAF para deixar o navegador aplicar display:block antes de medir.
  requestAnimationFrame(() => ensureMounted(pageId));
}

/**
 * Boot:
 *   - init() de TODAS as páginas (KPIs/tabelas/binds — não dependem de canvas).
 *   - mount() apenas da página inicial (que está visível).
 *   - Demais páginas só montam charts quando o usuário entrar nelas.
 */
export function bootstrap(initialPageId) {
  // init eager de todas — barato e síncrono.
  for (const id of handlers.keys()) ensureInited(id);

  // mount imediato da página visível.
  requestAnimationFrame(() => ensureMounted(initialPageId));

  // Delegação de eventos na barra de navegação — substitui `onclick` inline.
  const nav = document.getElementById("nav");
  if (nav) {
    nav.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-page]");
      if (!btn) return;
      go(btn.dataset.page, btn);
    });
  }
}


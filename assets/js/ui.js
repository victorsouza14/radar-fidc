import * as router from "./router.js";

const STORAGE_THEME   = "radar-theme";
const STORAGE_SIDEBAR = "radar-sidebar";

const MODE_META = {
  system: { icon: "monitor", label: "Tema: sistema" },
  light:  { icon: "sun",     label: "Tema: claro" },
  dark:   { icon: "moon",    label: "Tema: escuro" },
};

const $ = (id) => document.getElementById(id);
const app = () => $("app");
const matchMobile = () => window.matchMedia("(max-width: 768px)").matches;

export function tokenColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#000";
}

export function getThemeMode() {
  try {
    const v = localStorage.getItem(STORAGE_THEME);
    if (v === "light" || v === "dark") return v;
  } catch (_) {}
  return "system";
}

export function getResolvedTheme() {
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit === "light" || explicit === "dark") return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function setThemeMode(mode) {
  if (mode === "system") {
    try { localStorage.removeItem(STORAGE_THEME); } catch (_) {}
    document.documentElement.removeAttribute("data-theme");
  } else if (mode === "light" || mode === "dark") {
    try { localStorage.setItem(STORAGE_THEME, mode); } catch (_) {}
    document.documentElement.setAttribute("data-theme", mode);
  } else {
    return;
  }
  syncThemeUI();
  applyChartDefaults();
  refreshChartsTheme();
}

function syncThemeUI() {
  const mode = getThemeMode();
  const meta = MODE_META[mode];
  const icon  = $("theme-icon");
  const label = $("theme-label");
  const btn   = $("theme-toggle");
  if (icon)  icon.innerHTML = `<use href="#icon-${meta.icon}"/>`;
  if (label) label.textContent = meta.label;
  if (btn) {
    btn.setAttribute("aria-label", meta.label);
    btn.setAttribute("data-tooltip", meta.label);
  }
  document.querySelectorAll(".theme-option").forEach(opt => {
    opt.setAttribute("aria-checked", String(opt.dataset.mode === mode));
  });
}

function openThemeMenu() {
  const menu = $("theme-menu");
  const btn  = $("theme-toggle");
  if (!menu || !btn) return;
  menu.hidden = false;
  requestAnimationFrame(() => menu.classList.add("visible"));
  btn.setAttribute("aria-expanded", "true");
  hideTooltip();
}

function closeThemeMenu() {
  const menu = $("theme-menu");
  const btn  = $("theme-toggle");
  if (!menu || !btn) return;
  menu.classList.remove("visible");
  btn.setAttribute("aria-expanded", "false");
  setTimeout(() => { menu.hidden = true; }, 140);
}

function toggleThemeMenu() {
  const menu = $("theme-menu");
  if (!menu) return;
  if (menu.hidden) openThemeMenu(); else closeThemeMenu();
}

function syncSidebarToggleTooltip() {
  const btn = $("sidebar-toggle");
  if (!btn) return;
  const collapsed = app()?.dataset.sidebar === "collapsed";
  btn.setAttribute("data-tooltip", collapsed ? "Expandir (⌘\\)" : "Colapsar (⌘\\)");
  btn.setAttribute("aria-label",  collapsed ? "Expandir sidebar" : "Colapsar sidebar");
}

function applyStoredSidebar() {
  let state = "expanded";
  try { state = localStorage.getItem(STORAGE_SIDEBAR) || "expanded"; } catch (_) {}
  if (state === "collapsed") app().dataset.sidebar = "collapsed";
  syncSidebarToggleTooltip();
}

function toggleSidebar() {
  const a = app();
  if (!a) return;
  closeThemeMenu();

  if (matchMobile()) {
    a.dataset.sidebar = a.dataset.sidebar === "open" ? "" : "open";
    return;
  }

  const next = a.dataset.sidebar === "collapsed" ? "expanded" : "collapsed";
  if (next === "collapsed") a.dataset.sidebar = "collapsed";
  else a.removeAttribute("data-sidebar");
  try { localStorage.setItem(STORAGE_SIDEBAR, next); } catch (_) {}

  syncSidebarToggleTooltip();
  hideTooltip();
}

let tooltipEl = null;

function ensureTooltip() {
  if (tooltipEl) return tooltipEl;
  tooltipEl = document.createElement("div");
  tooltipEl.className = "tooltip-hover";
  tooltipEl.setAttribute("role", "tooltip");
  document.body.appendChild(tooltipEl);
  return tooltipEl;
}

function showTooltip(anchor) {
  const text = anchor.getAttribute("data-tooltip");
  if (!text) return;
  const el = ensureTooltip();
  el.textContent = text;
  const rect = anchor.getBoundingClientRect();
  el.style.left = `${rect.right + 10}px`;
  el.style.top  = `${rect.top + rect.height / 2}px`;
  el.classList.add("visible");
}

function hideTooltip() {
  tooltipEl?.classList.remove("visible");
}

function shouldShowTooltipFor(anchor) {
  const collapsed = app()?.dataset.sidebar === "collapsed";
  if (anchor.closest(".sidebar-nav")) return collapsed;
  if (anchor.id === "sidebar-toggle" || anchor.id === "theme-toggle") return collapsed;
  return false;
}

function bindTooltips() {
  document.body.addEventListener("mouseenter", (ev) => {
    const anchor = ev.target instanceof Element ? ev.target.closest("[data-tooltip]") : null;
    if (anchor && shouldShowTooltipFor(anchor)) showTooltip(anchor);
  }, true);
  document.body.addEventListener("mouseleave", (ev) => {
    if (ev.target instanceof Element && ev.target.closest("[data-tooltip]")) hideTooltip();
  }, true);
  window.addEventListener("scroll", hideTooltip, true);
  window.addEventListener("resize", hideTooltip);
}

function applyChartDefaults() {
  if (typeof window.Chart === "undefined") return;

  const fg       = tokenColor("--fg");
  const fgMuted  = tokenColor("--fg-muted");
  const fgSubtle = tokenColor("--fg-subtle");
  const border   = tokenColor("--divider");
  const C = window.Chart;

  C.defaults.font.family = "Inter, -apple-system, BlinkMacSystemFont, system-ui, sans-serif";
  C.defaults.font.size = 12;
  C.defaults.color = fgMuted;
  C.defaults.borderColor = border;

  Object.assign(C.defaults.plugins.legend.labels, {
    color: fg, boxWidth: 8, boxHeight: 8, usePointStyle: true, padding: 16,
  });
  Object.assign(C.defaults.plugins.tooltip, {
    backgroundColor: tokenColor("--bg-elev-3"),
    titleColor: fg,
    bodyColor: fgMuted,
    borderColor: tokenColor("--border"),
    borderWidth: 1,
    padding: 12,
    cornerRadius: 8,
    titleFont: { weight: "600", size: 12 },
    bodyFont:  { size: 12 },
    boxPadding: 4,
  });
  C.defaults.scale.ticks  = { ...(C.defaults.scale.ticks  || {}), color: fgSubtle };
  C.defaults.scale.grid   = { ...(C.defaults.scale.grid   || {}), color: border, drawTicks: false };
  C.defaults.scale.border = { ...(C.defaults.scale.border || {}), color: border };
}

function refreshChartsTheme() {
  router.remountAll();
}

const PAGE_SHORTCUTS = { g: "overview", f: "fidcs", m: "macro", c: "clientes", r: "match", s: "credit" };

function bindKeyboardShortcuts() {
  document.addEventListener("keydown", (ev) => {
    const meta = ev.metaKey || ev.ctrlKey;
    if (meta && ev.key === "\\") { ev.preventDefault(); toggleSidebar(); return; }
    if (meta && ev.key.toLowerCase() === "d") { ev.preventDefault(); toggleThemeMenu(); return; }

    const tag = (document.activeElement?.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (meta || ev.altKey) return;

    const target = PAGE_SHORTCUTS[ev.key.toLowerCase()];
    if (target) document.querySelector(`.nav-btn[data-page="${target}"]`)?.click();
  });
}

export function bootUI() {
  applyStoredSidebar();
  applyChartDefaults();
  syncThemeUI();
  bindTooltips();
  bindKeyboardShortcuts();

  $("sidebar-toggle")?.addEventListener("click", toggleSidebar);
  $("mobile-menu")?.addEventListener("click", toggleSidebar);
  $("sidebar-backdrop")?.addEventListener("click", () => app()?.removeAttribute("data-sidebar"));

  $("theme-toggle")?.addEventListener("click", (ev) => {
    ev.stopPropagation();
    toggleThemeMenu();
  });
  document.querySelectorAll(".theme-option").forEach(opt => {
    opt.addEventListener("click", () => {
      setThemeMode(opt.dataset.mode);
      closeThemeMenu();
    });
  });

  document.addEventListener("click", (ev) => {
    if (!ev.target.closest(".theme-menu-wrap")) closeThemeMenu();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeThemeMenu();
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (getThemeMode() === "system") {
      syncThemeUI();
      applyChartDefaults();
      refreshChartsTheme();
    }
  });
}

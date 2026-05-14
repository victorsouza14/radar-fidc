import { escapeHTML } from "../utils/format.js";

const CHEVRON_SVG = `<svg><use href="#icon-chevron-down"/></svg>`;
const CHECK_SVG   = `<svg class="opt-check"><use href="#icon-check"/></svg>`;

let openMenu = null;
let globalHandlersAttached = false;

function readOptions(select) {
  return Array.from(select.options).map(o => ({ value: o.value, label: o.textContent.trim() }));
}

function currentLabel(select) {
  return select.options[select.selectedIndex]?.textContent.trim() ?? "";
}

function positionMenu(btn, menu) {
  const rect = btn.getBoundingClientRect();
  const menuHeight = menu.scrollHeight || 200;
  const opensUp = (window.innerHeight - rect.bottom) < menuHeight + 16 && rect.top > menuHeight + 16;
  menu.classList.toggle("opens-up", opensUp);
}

function hideMenu(menu) {
  menu.classList.remove("visible");
  setTimeout(() => { menu.hidden = true; }, 140);
}

export function closeAllSelectMenus() {
  if (!openMenu) return;
  hideMenu(openMenu);
  document.querySelector(".select-btn[aria-expanded='true']")?.setAttribute("aria-expanded", "false");
  openMenu = null;
}

function attachGlobalHandlers() {
  if (globalHandlersAttached) return;
  globalHandlersAttached = true;
  document.addEventListener("click", (ev) => {
    if (openMenu && !ev.target.closest(".select-wrap")) closeAllSelectMenus();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeAllSelectMenus();
  });
}

function build(select) {
  select.classList.add("native-select");

  const wrap = document.createElement("div");
  wrap.className = "select-wrap";
  if (select.style.minWidth) wrap.style.minWidth = select.style.minWidth;
  select.parentNode.insertBefore(wrap, select);
  wrap.appendChild(select);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "select-btn";
  btn.setAttribute("aria-haspopup", "listbox");
  btn.setAttribute("aria-expanded", "false");
  btn.innerHTML = `<span class="select-value"></span>${CHEVRON_SVG}`;

  const menu = document.createElement("div");
  menu.className = "select-menu";
  menu.setAttribute("role", "listbox");
  menu.hidden = true;

  wrap.appendChild(btn);
  wrap.appendChild(menu);

  const valEl = btn.querySelector(".select-value");

  function renderOptions() {
    menu.innerHTML = readOptions(select).map(o => `
      <button type="button" class="select-option" role="option"
              data-value="${escapeHTML(o.value)}"
              aria-selected="${o.value === select.value}">
        <span>${escapeHTML(o.label)}</span>
        ${CHECK_SVG}
      </button>
    `).join("");
  }

  function syncTrigger() {
    valEl.textContent = currentLabel(select);
    btn.classList.toggle("is-placeholder", select.value === "");
  }

  function open() {
    if (openMenu && openMenu !== menu) closeAllSelectMenus();
    renderOptions();
    menu.hidden = false;
    requestAnimationFrame(() => menu.classList.add("visible"));
    btn.setAttribute("aria-expanded", "true");
    openMenu = menu;
    positionMenu(btn, menu);
  }

  function close() {
    hideMenu(menu);
    btn.setAttribute("aria-expanded", "false");
    if (openMenu === menu) openMenu = null;
  }

  btn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (menu.hidden) open(); else close();
  });

  menu.addEventListener("click", (ev) => {
    const opt = ev.target.closest(".select-option");
    if (!opt) return;
    select.value = opt.dataset.value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    syncTrigger();
    close();
  });

  select.addEventListener("change", syncTrigger);
  select.addEventListener("radar:sync", syncTrigger);

  new MutationObserver(() => {
    syncTrigger();
    if (!menu.hidden) renderOptions();
  }).observe(select, { childList: true });

  const reposition = () => { if (!menu.hidden) positionMenu(btn, menu); };
  window.addEventListener("resize", reposition);
  window.addEventListener("scroll", reposition, true);

  syncTrigger();
}

export function enhanceAllSelects(root = document) {
  attachGlobalHandlers();
  root.querySelectorAll("select.select:not(.native-select)").forEach(build);
}

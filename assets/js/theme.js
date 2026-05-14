import { tokenColor } from "./ui.js";

const RISCO_TOKEN = {
  BAIXO: "--data-positive",
  MEDIO: "--data-warning",
  ALTO:  "--data-negative",
};
const PERFIL_TOKEN = {
  CONSERVADOR: "--data-positive",
  MODERADO:    "--data-info",
  ARROJADO:    "--data-warning",
};
const RISCO_BADGE_CLASS = {
  BAIXO: "badge-A",
  MEDIO: "badge-B",
  ALTO:  "badge-D",
};

const resolve = (map, key, fallback = "--data-neutral") =>
  tokenColor(map[key] ?? fallback);

export const riscoColor  = (r) => resolve(RISCO_TOKEN, r);
export const perfilColor = (p) => resolve(PERFIL_TOKEN, p);
export const riscoBadge  = (r) => RISCO_BADGE_CLASS[r] ?? "badge-N";

export const rankBadgeClass = (rank) => (rank <= 3 ? "rank-top" : "");

// Paleta semântica — único lugar onde existe a tradução "domínio → cor".

export const RISCO_COLOR = {
  BAIXO: "#2E9B57",
  MEDIO: "#E8A33D",
  ALTO:  "#C0392B",
};

export const RISCO_BADGE = {
  BAIXO: "badge-A",
  MEDIO: "badge-B",
  ALTO:  "badge-D",
};

export const PERFIL_COLOR = {
  CONSERVADOR: "#2E9B57",
  MODERADO:    "#1F8045",
  ARROJADO:    "#E8A33D",
};

export const COTA_COLOR = {
  SENIOR:   "#093A1B",
  MEZANINO: "#1F8045",
  JUNIOR:   "#5BBF80",
  UNICA:    "#E8A33D",
};

const FALLBACK_COLOR = "#9AA8A0";
const FALLBACK_BADGE = "badge-C";

export const riscoColor = (r) => RISCO_COLOR[r] ?? FALLBACK_COLOR;
export const riscoBadge = (r) => RISCO_BADGE[r] ?? FALLBACK_BADGE;
export const perfilColor = (p) => PERFIL_COLOR[p] ?? FALLBACK_COLOR;
export const cotaColor  = (c) => COTA_COLOR[c]  ?? FALLBACK_COLOR;

export function rankBadgeClass(rank) {
  if (rank === 1) return "rank-1";
  if (rank === 2) return "rank-2";
  if (rank === 3) return "rank-3";
  return "rank-other";
}

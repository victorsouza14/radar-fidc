import { tokenColor } from "../ui.js";

const registry = new Map();

function applyGlobalDefaults() {
  if (typeof Chart === "undefined" || Chart._radarDefaultsApplied) return;
  Chart.defaults.animation = false;
  Chart.defaults.animations.colors = false;
  Chart.defaults.animations.x = false;
  Chart.defaults.animations.y = false;
  Chart.defaults.transitions.active.animation.duration = 0;
  Chart.defaults.responsive = true;
  Chart.defaults.maintainAspectRatio = false;
  Chart._radarDefaultsApplied = true;
}

function destroy(id) {
  const prev = registry.get(id);
  if (prev) { prev.destroy(); registry.delete(id); }
}

function ensureCanvas(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Canvas #${id} não encontrado.`);
  return el;
}

function render(id, config) {
  applyGlobalDefaults();
  destroy(id);
  const chart = new Chart(ensureCanvas(id), config);
  registry.set(id, chart);
  return chart;
}

const cardBg    = () => tokenColor("--bg-elev-1");
const gridColor = () => tokenColor("--divider");
const tickColor = () => tokenColor("--fg-subtle");

export function doughnut(id, labels, values, colors, total) {
  return render(id, {
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: cardBg() }] },
    options: {
      plugins: {
        legend: { position: "bottom", labels: { padding: 14 } },
        tooltip: {
          callbacks: {
            label: ctx => {
              const raw = Number(ctx.raw) || 0;
              const pct = total ? ` (${(raw / total * 100).toFixed(1)}%)` : "";
              return ` ${ctx.label}: ${raw.toLocaleString("pt-BR")}${pct}`;
            },
          },
        },
      },
      cutout: "68%",
    },
  });
}

export function pie(id, labels, values, colors) {
  return render(id, {
    type: "pie",
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: cardBg() }] },
    options: { plugins: { legend: { position: "bottom" } } },
  });
}

function bar({ id, labels, data, colors, tooltip, horizontal = false }) {
  const valueAxis = { grid: { color: gridColor(), drawTicks: false }, ticks: { color: tickColor() } };
  const labelAxis = {
    grid: { display: false },
    ticks: {
      color: tickColor(),
      font: { size: 11 },
      padding: 10,
      // horizontal: força mostrar todos os labels (top-10 não pode pular nomes);
      // vertical: deixa o Chart.js skipar se não couber (shortened labels já
      // ajudam, mas evita atropelo em viewports muito estreitas).
      crossAlign: horizontal ? "far" : "center",
      autoSkip: !horizontal,
    },
  };
  if (horizontal) valueAxis.ticks.callback = v => `${v}%`;

  return render(id, {
    type: "bar",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: colors, borderWidth: 1, borderRadius: 4 }] },
    options: {
      indexAxis: horizontal ? "y" : "x",
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: tooltip } },
      },
      scales: horizontal ? { x: valueAxis, y: labelAxis } : { x: labelAxis, y: valueAxis },
    },
  });
}

export function horizontalBar(id, labels, data, colors, tooltipLabel) {
  return bar({ id, labels, data, colors, tooltip: tooltipLabel, horizontal: true });
}

export function verticalBar(id, labels, data, colors, valueFormatter) {
  return bar({ id, labels, data, colors, tooltip: ctx => ` ${valueFormatter(ctx.raw, ctx)}` });
}


/**
 * Scatter (pontos) com eixo Y logarítmico — domina outliers de retorno
 * (alguns FIDCs com retorno >100% deformam escala linear).
 *
 * `groups` é um array de `{ label, color, points: [{x, y, meta}], ... }`.
 * Cada grupo vira um dataset (legend acende/apaga independentemente).
 *
 * Pontos com `y <= 0` são descartados silenciosamente (log não aceita).
 * `tooltipLabel(point)` deve devolver string formatada por ponto.
 */
export function scatterLogY({ id, groups, xLabel, yLabel, tooltipLabel }) {
  const datasets = groups.map(g => ({
    label: g.label,
    data: g.points.filter(p => p.y > 0),
    backgroundColor: g.color,
    borderColor: g.color,
    pointRadius: 3.5,
    pointHoverRadius: 6,
  }));

  return render(id, {
    type: "scatter",
    data: { datasets },
    options: {
      plugins: {
        legend: { position: "bottom", labels: { padding: 14, usePointStyle: true } },
        tooltip: {
          callbacks: {
            label: ctx => tooltipLabel ? tooltipLabel(ctx.raw) : ` ${ctx.raw.y}`,
          },
        },
      },
      scales: {
        x: {
          title: { display: !!xLabel, text: xLabel, color: tickColor() },
          grid: { color: gridColor() },
          ticks: { color: tickColor() },
        },
        y: {
          type: "logarithmic",
          title: { display: !!yLabel, text: yLabel, color: tickColor() },
          grid: { color: gridColor() },
          ticks: { color: tickColor() },
        },
      },
    },
  });
}


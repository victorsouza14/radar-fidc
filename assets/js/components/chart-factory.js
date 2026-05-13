// Factory de gráficos — Chart.js encapsulado, com registry + defaults perf-friendly.
// OCP: novos tipos se acrescentam aqui sem mudar quem chama.

const registry = new Map();

// Defaults globais — desligar animações pesadas + parsing desnecessário.
function applyGlobalDefaults() {
  if (typeof Chart === "undefined") return;
  if (Chart._radarDefaultsApplied) return;
  Chart.defaults.animation = false;          // sem animação (maior ganho de fps)
  Chart.defaults.animations.colors = false;
  Chart.defaults.animations.x = false;
  Chart.defaults.animations.y = false;
  Chart.defaults.transitions.active.animation.duration = 0;
  Chart.defaults.responsive = true;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 11;
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


/** Cria/atualiza um chart pelo id do canvas. */
export function render(id, config) {
  applyGlobalDefaults();
  destroy(id);
  const canvas = ensureCanvas(id);
  const chart = new Chart(canvas, config);
  registry.set(id, chart);
  return chart;
}

// ─── presets reutilizáveis ───

export function doughnut(id, labels, values, colors, total) {
  return render(id, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors, borderWidth: 3, borderColor: "#fff" }],
    },
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
      cutout: "62%",
    },
  });
}

export function horizontalBar(id, labels, data, colors, tooltipLabel) {
  return render(id, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors.map(c => c + "cc"),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 6,
      }],
    },
    options: {
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: tooltipLabel } },
      },
      scales: {
        x: { grid: { color: "#f0f0f0" }, ticks: { callback: v => `${v}%` } },
        y: { ticks: { font: { size: 11 } } },
      },
    },
  });
}

export function verticalBar(id, labels, data, colors, valueFormatter) {
  return render(id, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors.map(c => c + "cc"),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 8,
      }],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${valueFormatter(ctx.raw)}` } },
      },
      scales: { y: { grid: { color: "#f0f0f0" } } },
    },
  });
}

export function scatter(id, points, colorFn, tooltipFn) {
  // Pré-computa cores e dados num único pass — evita 2 .map() em datasets grandes.
  const data = new Array(points.length);
  const colors = new Array(points.length);
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    data[i] = { x: p.x, y: p.y, _meta: p };
    colors[i] = colorFn(p) + "99";
  }
  return render(id, {
    type: "scatter",
    data: {
      datasets: [{
        data,
        backgroundColor: colors,
        pointRadius: 4,         // menor = menos pixels para desenhar
        pointHoverRadius: 7,
      }],
    },
    options: {
      parsing: false,           // dados já estão no formato {x,y}
      animation: false,
      plugins: {
        legend: { display: false },
        decimation: { enabled: true, algorithm: "min-max" },
        tooltip: { callbacks: { label: ctx => tooltipFn(ctx.raw._meta) } },
      },
      scales: {
        x: { title: { display: true, text: "Score de Risco" }, grid: { color: "#f0f0f0" }, min: 0, max: 100 },
        y: { title: { display: true, text: "Retorno anual (%)" }, grid: { color: "#f0f0f0" }, ticks: { callback: v => `${v}%` } },
      },
    },
  });
}

export function pie(id, labels, data, colors) {
  return render(id, {
    type: "pie",
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderWidth: 3, borderColor: "#fff" }],
    },
    options: {
      plugins: { legend: { position: "bottom" } },
    },
  });
}

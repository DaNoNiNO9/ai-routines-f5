/* Forja: progressive enhancement only. Pages work without this file. */
(function () {
  "use strict";

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function readJson(id) {
    var element = document.getElementById(id);
    if (!element) {
      return null;
    }
    try {
      return JSON.parse(element.textContent);
    } catch (error) {
      console.error("Datos de gráfica inválidos en #" + id, error);
      return null;
    }
  }

  function weightChart(canvas, data) {
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: data.weight_label,
            data: data.weight,
            borderColor: cssVar("--text-muted"),
            backgroundColor: cssVar("--text-muted"),
            pointRadius: 3,
            borderWidth: 1,
            tension: 0
          },
          {
            label: data.average_label,
            data: data.average,
            borderColor: cssVar("--accent"),
            backgroundColor: cssVar("--accent"),
            pointRadius: 0,
            borderWidth: 3,
            spanGaps: true,
            tension: 0.3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: { y: { title: { display: true, text: "kg" } } },
        plugins: { legend: { position: "bottom" } }
      }
    });
  }

  function doughnutChart(canvas, data) {
    return new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: data.labels,
        datasets: [
          {
            data: data.values,
            backgroundColor: [cssVar("--accent"), cssVar("--success"), cssVar("--warning")],
            borderWidth: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: { legend: { position: "bottom" } }
      }
    });
  }

  function barChart(canvas, data) {
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [{ data: data.values, backgroundColor: cssVar("--accent"), borderRadius: 6 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: "kcal" } } }
      }
    });
  }

  var builders = { weight: weightChart, doughnut: doughnutChart, bars: barChart };

  function buildCharts() {
    if (typeof window.Chart === "undefined") {
      return;
    }
    Chart.defaults.color = cssVar("--text-muted");
    Chart.defaults.borderColor = cssVar("--border");
    Chart.defaults.font.family = cssVar("--font-body") || Chart.defaults.font.family;
    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var data = readJson(canvas.dataset.chart);
      var build = builders[canvas.dataset.kind];
      if (data && build) {
        build(canvas, data);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", buildCharts);
})();

/* Alza: progressive enhancement only. Pages work without this file. */
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

/* Phase 10: multi-series line chart, rest timer and elapsed time (Alpine components). */
(function () {
  "use strict";

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (typeof window.Chart === "undefined") {
      return;
    }
    document.querySelectorAll('canvas[data-kind="lines"]').forEach(function (canvas) {
      var element = document.getElementById(canvas.dataset.chart);
      if (!element) {
        return;
      }
      var data;
      try {
        data = JSON.parse(element.textContent);
      } catch (error) {
        console.error("Datos de gráfica inválidos en #" + canvas.dataset.chart, error);
        return;
      }
      var colours = [cssVar("--accent"), cssVar("--text-muted")];
      new Chart(canvas, {
        type: "line",
        data: {
          labels: data.labels,
          datasets: data.series.map(function (series, index) {
            return {
              label: series.label,
              data: series.data,
              borderColor: colours[index % colours.length],
              backgroundColor: colours[index % colours.length],
              borderWidth: index === 0 ? 3 : 1,
              pointRadius: 3,
              tension: 0.2
            };
          })
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: { y: { title: { display: true, text: "kg" } } },
          plugins: { legend: { position: "bottom" } }
        }
      });
    });
  });

  document.addEventListener("alpine:init", function () {
    Alpine.data("restTimer", function (seconds, startedAt) {
      return {
        total: seconds,
        startedAt: startedAt || Math.floor(Date.now() / 1000),
        remaining: seconds,
        visible: true,
        done: false,
        handle: null,
        get display() {
          var minutes = Math.floor(this.remaining / 60);
          var rest = this.remaining % 60;
          return minutes + ":" + (rest < 10 ? "0" : "") + rest;
        },
        init: function () {
          this.tick();
          this.handle = setInterval(this.tick.bind(this), 1000);
        },
        tick: function () {
          var elapsed = Math.floor(Date.now() / 1000) - this.startedAt;
          this.remaining = Math.max(0, this.total - elapsed);
          if (this.remaining === 0 && !this.done) {
            this.done = true;
            if (navigator.vibrate) {
              navigator.vibrate([200, 100, 200]);
            }
          }
        },
        extend: function (extra) {
          this.total += extra;
          this.done = false;
          this.tick();
        }
      };
    });

    Alpine.data("elapsed", function (startedAt) {
      return {
        text: "",
        init: function () {
          var update = function () {
            var seconds = Math.max(0, Math.floor(Date.now() / 1000) - startedAt);
            this.text = Math.floor(seconds / 60) + " min";
          }.bind(this);
          update();
          setInterval(update, 15000);
        }
      };
    });
  });
})();

/* Estado de carga: el botón pulsado deja de estarlo hasta que llega la página nueva. */
(function () {
  "use strict";

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || form.hasAttribute("data-sin-carga")) {
      return;
    }
    var button = form.querySelector("button[type='submit'], button:not([type])");
    if (button && !button.classList.contains("is-loading")) {
      button.classList.add("is-loading");
    }
  });

  /* Al volver atrás el navegador restaura el DOM: el botón no puede quedarse girando. */
  window.addEventListener("pageshow", function () {
    document.querySelectorAll(".button.is-loading").forEach(function (button) {
      button.classList.remove("is-loading");
    });
  });
})();

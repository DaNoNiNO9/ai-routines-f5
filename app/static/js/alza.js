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

/* Ficha de ejercicio: los enlaces con data-sheet la abren encima, sin salir de la sesión.
   Sin JavaScript (o si algo falla) el enlace lleva a la página de la ficha. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function prepareVideos(root) {
    root.querySelectorAll("video[data-pausable]").forEach(function (video) {
      if (reduceMotion) {
        video.removeAttribute("autoplay");
        video.pause();
        video.controls = true;
        return;
      }
      video.addEventListener("click", function () {
        if (video.paused) {
          video.play();
        } else {
          video.pause();
        }
      });
    });
  }

  function dialog() {
    var existing = document.getElementById("exercise-sheet");
    if (existing) {
      return existing;
    }
    var template = document.getElementById("sheet-template");
    if (!template) {
      return null;
    }
    document.body.appendChild(template.content.cloneNode(true));
    var created = document.getElementById("exercise-sheet");
    created.addEventListener("click", function (event) {
      if (event.target === created) {
        created.close();
      }
    });
    created.addEventListener("close", function () {
      created.querySelectorAll("video").forEach(function (video) { video.pause(); });
      created.querySelector(".sheet-body").innerHTML = "";
    });
    return created;
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-sheet]");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) {
      return;
    }
    var sheet = dialog();
    if (!sheet || typeof sheet.showModal !== "function") {
      return;
    }
    event.preventDefault();
    var url = link.href + (link.href.indexOf("?") === -1 ? "?" : "&") + "parcial=1";
    fetch(url, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        var body = sheet.querySelector(".sheet-body");
        body.innerHTML = html;
        prepareVideos(body);
        sheet.showModal();
      })
      .catch(function () {
        window.location.href = link.href;
      });
  });

  document.addEventListener("DOMContentLoaded", function () {
    prepareVideos(document);
  });
})();

/* App instalable y sin cobertura: service worker, series en cola, pantalla encendida
   durante la sesión y el botón de instalar. Todo es opcional: sin soporte, la app
   funciona igual que antes. */
(function () {
  "use strict";

  var QUEUE_KEY = "alza-series-pendientes";
  var texts = {};
  try {
    texts = JSON.parse(document.getElementById("i18n-js").textContent);
  } catch (error) {
    texts = {};
  }

  /* --- Service worker --- */
  if ("serviceWorker" in navigator && document.body.dataset.sw) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register(document.body.dataset.sw, { scope: "/" }).catch(function (error) {
        console.warn("No se pudo registrar el service worker", error);
      });
    });
  }

  /* --- Cola de series --- */
  function readQueue() {
    try {
      return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
    } catch (error) {
      return [];
    }
  }

  function writeQueue(queue) {
    try {
      if (queue.length) {
        localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
      } else {
        localStorage.removeItem(QUEUE_KEY);
      }
    } catch (error) {
      /* Sin almacenamiento (modo privado): la serie no se puede guardar. */
    }
  }

  function notice(text, kind) {
    var list = document.querySelector(".flashes");
    if (!list) {
      list = document.createElement("ul");
      list.className = "flashes";
      list.setAttribute("role", "status");
      list.setAttribute("aria-live", "polite");
      var main = document.getElementById("main");
      if (!main) {
        return;
      }
      main.insertBefore(list, main.firstChild);
    }
    var item = document.createElement("li");
    item.className = "flash flash-" + (kind || "info");
    item.textContent = text;
    list.appendChild(item);
  }

  function markPending(form, fields) {
    var row = form.closest(".set-row");
    var values = {};
    fields.forEach(function (pair) { values[pair[0]] = pair[1]; });
    var text = document.createElement("span");
    text.className = "set-values";
    var number = new Intl.NumberFormat(document.documentElement.lang || "es", { maximumFractionDigits: 2 });
    var kilos = number.format(Number(String(values.weight_kg || "0").replace(",", ".")));
    text.textContent = kilos + " kg \u00d7 " + (values.reps || "0") + " \u00b7 " + (texts.pending || "");
    var index = document.createElement("span");
    index.className = "set-index";
    index.textContent = values.set_index || "";
    row.classList.add("set-done", "set-pending");
    row.replaceChildren(index, text);
  }

  function send(entry) {
    var body = new URLSearchParams();
    entry.fields.forEach(function (pair) { body.append(pair[0], pair[1]); });
    return fetch(entry.action, { method: "POST", body: body, credentials: "same-origin" });
  }

  var flushing = false;
  function flush() {
    var queue = readQueue();
    if (!queue.length || flushing) {
      return;
    }
    flushing = true;
    var chain = Promise.resolve();
    queue.forEach(function () {
      chain = chain.then(function () {
        var current = readQueue();
        if (!current.length) {
          return null;
        }
        return send(current[0]).then(function () {
          /* Entregada (sea cual sea la respuesta): fuera de la cola. Repetirla no
             duplica nada: el servidor sobrescribe la misma serie. */
          writeQueue(readQueue().slice(1));
        });
      });
    });
    chain.then(function () {
      flushing = false;
      notice(texts.queue_sent || "", "success");
      if (document.querySelector("[data-wake-lock]")) {
        window.location.reload();
      }
    }).catch(function () {
      flushing = false; /* Sigue sin red: se reintenta con el siguiente «online». */
      notice(texts.queue_waiting || "", "warning");
    });
  }

  /* La copia guardada de la sesión es de antes de apuntar: las series en cola se
     vuelven a marcar como pendientes para que nadie las apunte dos veces. */
  function showQueued() {
    readQueue().forEach(function (entry) {
      var wanted = {};
      entry.fields.forEach(function (pair) { wanted[pair[0]] = pair[1]; });
      document.querySelectorAll("form.set-form").forEach(function (form) {
        var same = form.action === entry.action &&
          form.elements.routine_exercise_id && form.elements.routine_exercise_id.value === wanted.routine_exercise_id &&
          form.elements.set_index && form.elements.set_index.value === wanted.set_index;
        if (same) {
          markPending(form, entry.fields);
        }
      });
    });
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (form.hasAttribute("data-logout")) {
      writeQueue([]);
      if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage("logout");
      }
      return;
    }
    if (!form.classList.contains("set-form") || !window.fetch) {
      return;
    }
    event.preventDefault();
    var fields = Array.from(new FormData(form).entries());
    var entry = { action: form.action, fields: fields };
    send(entry).then(function (response) {
      window.location.href = response.url;
    }).catch(function () {
      var queue = readQueue();
      queue.push(entry);
      writeQueue(queue);
      markPending(form, fields);
      notice(texts.queued || "", "warning");
    });
  });

  window.addEventListener("online", flush);
  document.addEventListener("DOMContentLoaded", function () {
    if (readQueue().length) {
      showQueued();
      if (navigator.onLine) {
        flush();
      } else {
        notice(texts.queue_waiting || "", "warning");
      }
    }
  });

  /* --- Pantalla encendida durante la sesión --- */
  var wakeLock = null;
  function keepAwake() {
    if (!document.querySelector("[data-wake-lock]") || !("wakeLock" in navigator)) {
      return;
    }
    navigator.wakeLock.request("screen").then(function (lock) {
      wakeLock = lock;
    }).catch(function () { /* Batería baja o el navegador no lo permite. */ });
  }
  document.addEventListener("DOMContentLoaded", keepAwake);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && (!wakeLock || wakeLock.released)) {
      keepAwake();
    }
  });

  /* --- Botón de instalar (Android y escritorio; en iPhone se explica con texto) --- */
  var installEvent = null;
  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    installEvent = event;
    document.querySelectorAll("[data-install]").forEach(function (box) { box.hidden = false; });
  });
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-install-button]");
    if (!button || !installEvent) {
      return;
    }
    installEvent.prompt();
    installEvent.userChoice.finally(function () {
      installEvent = null;
      document.querySelectorAll("[data-install]").forEach(function (box) { box.hidden = true; });
    });
  });
})();

/* Marca nueva: una vibración corta para celebrarla (si el móvil vibra y no se pidió menos movimiento). */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduce && document.querySelector("[data-vibrate]") && navigator.vibrate) {
    navigator.vibrate([80, 60, 80, 60, 160]);
  }
});

/* Código de barras con la cámara.
   1) Lector propio del navegador (BarcodeDetector: Chrome y Edge en Android), si lee EAN/UPC.
   2) Si no, ZXing en JavaScript con la cámara (getUserMedia): Safari en iPhone, escritorio.
      La librería (430 KB) solo se descarga al pulsar «Escanear».
   3) Sin cámara (por ejemplo, sin HTTPS), queda la entrada a mano con su explicación. */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  var form = document.querySelector("form[data-barcode]");
  var button = form && form.querySelector("[data-scan]");
  var box = document.querySelector("[data-scanner]");
  var canUseCamera = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && window.isSecureContext;
  if (!button || !box || !canUseCamera) {
    return;
  }
  var video = box.querySelector("video");
  var wanted = ["ean_13", "ean_8", "upc_a", "upc_e"];
  var forceZxing = /[?&]lector=zxing\b/.test(window.location.search);
  var stopCurrent = null;

  function showButton() {
    button.hidden = false;
    document.querySelectorAll("[data-no-scan]").forEach(function (hint) { hint.hidden = true; });
  }

  function found(code) {
    stop();
    form.elements.codigo.value = code;
    form.requestSubmit();
  }

  function stop() {
    if (stopCurrent) {
      stopCurrent();
      stopCurrent = null;
    }
    box.hidden = true;
  }

  function startNative() {
    var detector = new window.BarcodeDetector({ formats: wanted });
    var running = true;
    var stream = null;
    stopCurrent = function () {
      running = false;
      if (stream) {
        stream.getTracks().forEach(function (track) { track.stop(); });
      }
    };
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then(function (media) {
        stream = media;
        video.srcObject = media;
        box.hidden = false;
        return video.play();
      })
      .then(function () {
        var look = function () {
          if (!running) {
            return;
          }
          detector.detect(video).then(function (codes) {
            if (codes.length) {
              found(codes[0].rawValue);
            } else {
              setTimeout(look, 250);
            }
          }).catch(function () { setTimeout(look, 500); });
        };
        look();
      })
      .catch(stop);
  }

  function loadZxing() {
    if (window.ZXingBrowser) {
      return Promise.resolve(window.ZXingBrowser);
    }
    return new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = form.dataset.zxing;
      script.onload = function () { resolve(window.ZXingBrowser); };
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function startZxing() {
    box.hidden = false;
    loadZxing().then(function (ZXing) {
      var reader = new ZXing.BrowserMultiFormatReader();
      return reader.decodeFromConstraints(
        { video: { facingMode: "environment" }, audio: false },
        video,
        function (result, error, controls) {
          if (result) {
            controls.stop();
            found(result.getText());
          }
        }
      );
    }).then(function (controls) {
      stopCurrent = function () { controls.stop(); };
    }).catch(stop);
  }

  var native = Promise.resolve(false);
  if ("BarcodeDetector" in window && !forceZxing) {
    native = window.BarcodeDetector.getSupportedFormats().then(function (formats) {
      return wanted.some(function (format) { return formats.indexOf(format) !== -1; });
    }).catch(function () { return false; });
  }
  native.then(function (hasNative) {
    showButton();
    button.dataset.reader = hasNative ? "native" : "zxing";
    button.addEventListener("click", function () {
      if (hasNative) {
        startNative();
      } else {
        startZxing();
      }
    });
  });
  box.querySelector("[data-scan-stop]").addEventListener("click", stop);
  window.addEventListener("pagehide", stop);
});

/* Ayuda a demanda: el «?» abre su <dialog> como modal. Sin JavaScript (o sin
   showModal) el enlace al id funciona igual gracias a :target en el CSS. */
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest && event.target.closest("a[data-help]");
    if (trigger) {
      var box = document.getElementById(trigger.getAttribute("data-help"));
      if (box && typeof box.showModal === "function") {
        event.preventDefault();
        box.showModal();
      }
      return;
    }
    var close = event.target.closest && event.target.closest("[data-help-close]");
    if (close) {
      var open = close.closest("dialog");
      if (open && open.open) {
        event.preventDefault();
        open.close();
      }
      return;
    }
    // Tocar fuera del contenido (el fondo) también cierra.
    if (event.target.classList && event.target.classList.contains("help-dialog") && event.target.open) {
      event.target.close();
    }
  });
})();

/* Alza service worker: la app sigue abriendo en un gimnasio sin cobertura.

   - Páginas: primero la red; sin red, la última copia que se vio de esa página
     y, si no hay, /sin-conexion. Solo se guardan las páginas de uso diario.
   - Estáticos (CSS, JS, fuentes, imágenes): se sirven de la caché y se
     actualizan por detrás.
   - Vídeos: siempre de la red (piden rangos y pesan; no se guardan).
   - La versión viene en la URL de registro (/sw.js?v=X): con cada versión de la
     app se instala un service worker nuevo que borra las cachés viejas.
   - Al cerrar sesión la página avisa y se borran las páginas guardadas. */
"use strict";

var VERSION = new URL(self.location.href).searchParams.get("v") || "dev";
var STATIC_CACHE = "alza-static-" + VERSION;
var PAGES_CACHE = "alza-pages-" + VERSION;
var OFFLINE_URL = "/sin-conexion";
var PRECACHE = [
  OFFLINE_URL,
  "/static/css/app.css",
  "/static/css/fonts.css",
  "/static/js/alza.js",
  "/static/vendor/alpine-3.17.2.min.js",
  "/static/img/favicon.svg",
  "/static/img/icon-192.png"
];
/* Páginas que merece la pena tener sin red: las de entrenar y apuntar. */
var CACHEABLE_PAGES = /^\/(panel|nutricion|diario|entrenamiento(\/.*)?|entreno\/\d+(\/resumen)?|entreno\/historial)$/;

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) { return cache.addAll(PRECACHE); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (key) {
        return key.indexOf("alza-") === 0 && key !== STATIC_CACHE && key !== PAGES_CACHE;
      }).map(function (key) { return caches.delete(key); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("message", function (event) {
  if (event.data === "logout") {
    caches.delete(PAGES_CACHE);
  }
});

function fromNetworkFirst(request) {
  var url = new URL(request.url);
  return fetch(request).then(function (response) {
    if (response.ok && !response.redirected && CACHEABLE_PAGES.test(url.pathname)) {
      var copy = response.clone();
      caches.open(PAGES_CACHE).then(function (cache) { cache.put(request, copy); });
    }
    return response;
  }).catch(function () {
    return caches.match(request, { ignoreSearch: true }).then(function (cached) {
      return cached || caches.match(OFFLINE_URL);
    });
  });
}

function fromCacheThenRefresh(request) {
  return caches.open(STATIC_CACHE).then(function (cache) {
    return cache.match(request).then(function (cached) {
      var refresh = fetch(request).then(function (response) {
        if (response.ok) {
          cache.put(request, response.clone());
        }
        return response;
      }).catch(function () { return cached; });
      return cached || refresh;
    });
  });
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") {
    return;
  }
  var url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.indexOf("/static/video/") === 0) {
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fromNetworkFirst(request));
  } else if (url.pathname.indexOf("/static/") === 0) {
    event.respondWith(fromCacheThenRefresh(request));
  }
});

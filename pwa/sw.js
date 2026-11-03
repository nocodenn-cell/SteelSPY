/* Cache mínimo da casca; nunca cachear API, conferência ou PDF (sempre rede). */
const SHELL = [
  "./index.html",
  "./manifest.json",
  "./sw.js",
  "./assets/app.css",
  "./js/main.js",
  "./js/config.js",
  "./js/api.js",
  "./js/render.js",
  "./js/sessao.js",
  "./js/roteador.js",
  "./js/telas_entrada.js",
  "./js/telas_compra.js",
  "./js/telas_recebimento.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open("steelspy-v4").then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((chaves) => Promise.all(chaves.filter((k) => k !== "steelspy-v4").map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

/**
 * Só a casca é servida do cache. Qualquer caminho de API passa direto: dado de
 * conciliação velho na tela do portão é pior que nenhuma tela.
 */
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  if (url.origin !== self.location.origin) {
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("./index.html")),
    );
    return;
  }
  const eStatico = /^\/(js|assets)\//.test(url.pathname);
  if (eStatico) {
    event.respondWith(caches.match(event.request).then((r) => r || fetch(event.request)));
  }
});

/* Cache mínimo da casca; nunca cachear /conferir (sempre rede). */
const SHELL = ["./index.html", "./manifest.json", "./sw.js", "./assets/app.css"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open("steelspy-v2").then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

/** Não interceptar: API, conferência e PDFs (sempre rede). */
const PATHS_IGNORAR = ["/conferir", "/laudo.pdf", "/divergencias.pdf"];

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.includes("/api/")) {
    return;
  }
  if (
    url.pathname.endsWith("/conferir") ||
    PATHS_IGNORAR.some((p) => url.pathname.includes(p))
  ) {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("./index.html")),
    );
  }
});

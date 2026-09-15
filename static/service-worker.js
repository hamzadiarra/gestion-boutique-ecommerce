const CACHE_NAME = "gestion-boutique-shell-v2-delivery-private";
const STATIC_ASSETS = [
  "/",
  "/static/css/style.css",
  "/static/js/animations.js",
  "/static/js/offline-manager.js",
  "/static/manifest.webmanifest",
  "/static/images/boutique_hero_bg.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) return caches.delete(key);
          return undefined;
        }),
      )
    ).then(() => self.clients.claim())
  );
});

function isNavigationRequest(request) {
  return request.mode === "navigate"
    || request.headers.get("accept")?.includes("text/html");
}

function isApiOfflineSync(request) {
  return request.url.includes("/offline/sync/");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;

  if (request.method !== "GET") {
    return;
  }

  // Financial pages and expense attachments must never enter a shared cache.
  if (new URL(request.url).pathname.startsWith("/dashboard/comptable/") || ["/orders/", "/dashboard/livreur/", "/dashboard/livraisons/", "/dashboard/vendeur/commandes/"].some(prefix => new URL(request.url).pathname.startsWith(prefix))) {
    event.respondWith(fetch(request, { cache: "no-store" }).catch(() =>
      new Response("Cet espace financier nécessite une connexion Internet.", {
        status: 503, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
      })
    ));
    return;
  }

  if (isApiOfflineSync(request)) {
    event.respondWith(
      fetch(request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      }).catch(async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        return new Response(JSON.stringify({ ok: false, payload: null, error: "offline" }), {
          headers: { "Content-Type": "application/json" },
          status: 503,
        });
      })
    );
    return;
  }

  if (isNavigationRequest(request)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            return response;
          }
          throw new Error("non-ok response");
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (cached) return cached;
          const shell = await caches.match("/");
          return shell || Response.error();
        })
    );
    return;
  }

  if (request.url.startsWith(location.origin + "/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      }))
    );
  }
});

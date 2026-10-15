const CACHE_NAME = "gestion-boutique-shell-v5-private-safe";
const STATIC_ASSETS = [
  "/static/css/style.css",
  "/static/css/refonte.css",
  "/static/js/refonte.js",
  "/static/js/animations.js",
  "/static/js/offline-manager.js",
  "/static/manifest.webmanifest",
  "/static/images/boutique_hero_bg.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      await cache.addAll(STATIC_ASSETS);
      // The offline shell must never contain the installing user's account data.
      const shell = await fetch(new Request("/", { credentials: "omit", cache: "no-store" }));
      if (shell.ok) await cache.put("/", shell);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key.startsWith("gestion-boutique-shell-") && key !== CACHE_NAME) return caches.delete(key);
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

  const path = new URL(request.url).pathname;
  const privatePath = ["/accounts/", "/admin/", "/cart/", "/dashboard/", "/notifications/", "/orders/", "/payments/"]
    .some(prefix => path.startsWith(prefix));
  if (privatePath || isApiOfflineSync(request)) {
    event.respondWith(fetch(request, { cache: "no-store" }).catch(() =>
      new Response(isApiOfflineSync(request)
        ? JSON.stringify({ ok: false, payload: null, error: "offline" })
        : "Cet espace privé nécessite une connexion Internet.", {
        status: 503,
        headers: {
          "Content-Type": isApiOfflineSync(request) ? "application/json" : "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
        },
      })
    ));
    return;
  }

  if (isNavigationRequest(request)) {
    // HTML includes account navigation and CSRF tokens, even on public pages.
    // Only the explicitly anonymous install-time shell may be used offline.
    event.respondWith(fetch(request, { cache: "no-store" }).catch(async () => {
      const cache = await caches.open(CACHE_NAME);
      const shell = await cache.match("/");
      return shell || new Response("Connexion Internet nécessaire.", {
        status: 503, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
      });
    }));
    return;
  }

  if (request.url.startsWith(location.origin + "/static/")) {
    event.respondWith(
      caches.open(CACHE_NAME).then(cache => cache.match(request)).then((cached) => cached || fetch(request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      }))
    );
  }
});

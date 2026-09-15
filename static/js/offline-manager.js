(() => {
  const i18n = document.getElementById("offline-i18n")?.dataset || {};
  const DB_NAME = "gestion-boutique-offline";
  const DB_VERSION = 1;
  const STORES = {
    meta: "meta",
    categories: "categories",
    products: "products",
    orders: "orders",
    notifications: "notifications",
    seller_orders: "seller_orders",
  };

  const state = {
    userId: document.body?.dataset?.userId || null,
    isAuthenticated: document.body?.dataset?.userAuthenticated === "1",
    isOnline: navigator.onLine,
  };

  function showOfflineBanner(online) {
    const banner = document.getElementById("offline-status-banner");
    if (!banner) return;
    const label = online ? (i18n.online || "En ligne") : (i18n.offline || "Hors connexion");

    getLastSyncText().then((lastSync) => {
      banner.textContent = `${label} — ${i18n.lastSync || "Dernière synchronisation"} : ${lastSync}`;
      banner.classList.toggle("online", online);
      banner.classList.remove("d-none");
      banner.hidden = false;

      if (online) {
        window.setTimeout(() => {
          banner.hidden = true;
          banner.classList.add("d-none");
          banner.classList.remove("online");
        }, 1800);
      }
    });
  }

  function getBodyMessage() {
    let statusNode = document.getElementById("offline-status-body-message");
    if (statusNode) return statusNode;

    const root = document.querySelector("main");
    if (!root) return null;

    statusNode = document.createElement("div");
    statusNode.id = "offline-status-body-message";
    statusNode.className = "offline-offline-message container";
    root.prepend(statusNode);
    return statusNode;
  }

  function showNoDataMessage() {
    const zone = getBodyMessage();
    if (!zone) return;
    zone.textContent = i18n.noData || "Cette information n'est pas disponible hors connexion.";
  }

  function clearNoDataMessage() {
    const zone = document.getElementById("offline-status-body-message");
    if (zone) zone.textContent = "";
  }

  function notifyOfflineActionBlocked() {
    const existing = document.querySelector(".offline-action-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "offline-action-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "assertive");
    toast.textContent = i18n.blocked || "Cette action nécessite une connexion Internet.";
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 250);
    }, 2500);
  }

  function withIndexedDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        Object.values(STORES).forEach((storeName) => {
          if (!db.objectStoreNames.contains(storeName)) {
            db.createObjectStore(storeName, { keyPath: "id", autoIncrement: true });
          }
        });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function dbPutMany(db, storeName, items, scope = null) {
    return new Promise((resolve) => {
      if (!db.objectStoreNames.contains(storeName)) {
        resolve();
        return;
      }

      const tx = db.transaction(storeName, "readwrite");
      const store = tx.objectStore(storeName);

      if (Array.isArray(items)) {
        for (const item of items) {
          const record = {
            ...item,
            scopeKey: scope ? `${scope}` : "public",
          };
          store.put(record);
        }
      }

      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  }

  function dbSetMeta(db, key, value) {
    return new Promise((resolve) => {
      if (!db.objectStoreNames.contains(STORES.meta)) {
        resolve();
        return;
      }
      const tx = db.transaction(STORES.meta, "readwrite");
      const store = tx.objectStore(STORES.meta);
      store.put({ id: key, ...value });
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  }

  function dbGetMeta(db, key) {
    return new Promise((resolve) => {
      if (!db.objectStoreNames.contains(STORES.meta)) {
        resolve(null);
        return;
      }
      const tx = db.transaction(STORES.meta, "readonly");
      const store = tx.objectStore(STORES.meta);
      const req = store.get(key);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  }

  function dbClearStoreByScope(db, storeName, scope) {
    return new Promise((resolve) => {
      if (!db.objectStoreNames.contains(storeName)) {
        resolve();
        return;
      }

      const tx = db.transaction(storeName, "readwrite");
      const store = tx.objectStore(storeName);
      const req = store.openCursor();

      req.onsuccess = () => {
        const cursor = req.result;
        if (!cursor) return;
        if (!scope || cursor.value.scopeKey === scope) {
          store.delete(cursor.key);
        }
        cursor.continue();
      };
      req.onerror = () => resolve();
      tx.oncomplete = () => resolve();
    });
  }

  function clearPrivateUserData() {
    if (!state.userId) return Promise.resolve();

    return withIndexedDB()
      .then((db) => Promise.all([
        dbClearStoreByScope(db, STORES.orders, String(state.userId)),
        dbClearStoreByScope(db, STORES.notifications, String(state.userId)),
        dbClearStoreByScope(db, STORES.seller_orders, String(state.userId)),
      ]).then(() => db.close()));
  }

  function clearAllPublicCache() {
    return withIndexedDB()
      .then((db) => Promise.all([
        dbClearStoreByScope(db, STORES.categories, "public"),
        dbClearStoreByScope(db, STORES.products, "public"),
        dbClearStoreByScope(db, STORES.meta, "meta"),
      ]).then(() => db.close()));
  }

  async function getStoreCount(db, storeName, scope) {
    return new Promise((resolve) => {
      if (!db.objectStoreNames.contains(storeName)) {
        resolve(0);
        return;
      }
      const tx = db.transaction(storeName, "readonly");
      const store = tx.objectStore(storeName);
      const req = store.openCursor();
      let count = 0;

      req.onsuccess = (event) => {
        const cursor = event.target.result;
        if (!cursor) {
          resolve(count);
          return;
        }
        const record = cursor.value;
        if (record.scopeKey === scope || scope == null) {
          count += 1;
        }
        cursor.continue();
      };
      req.onerror = () => resolve(0);
    });
  }

  async function getLastSyncText() {
    const fallback = "jamais";
    try {
      const db = await withIndexedDB();
      const meta = await dbGetMeta(db, `last_sync_${state.userId || "guest"}`);
      db.close();
      if (!meta || !meta.value) return fallback;
      const date = new Date(meta.value);
      if (Number.isNaN(date.getTime())) return fallback;
      return new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(date);
    } catch (_error) {
      return fallback;
    }
  }

  async function syncNow() {
    try {
      const response = await fetch("/offline/sync/", {
        method: "GET",
        headers: { "Accept": "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) return false;

      const body = await response.json();
      if (!body?.ok || !body.payload) return false;

      const data = body.payload;
      const db = await withIndexedDB();
      await dbPutMany(db, STORES.categories, data.categories || [], "public");
      await dbPutMany(db, STORES.products, data.products || [], "public");

      if (state.isAuthenticated && data.user?.id) {
        const userScope = String(data.user.id);
        await Promise.all([
          dbPutMany(db, STORES.orders, data.orders || [], userScope),
          dbPutMany(db, STORES.notifications, data.notifications || [], userScope),
          dbPutMany(db, STORES.seller_orders, data.seller_orders || [], userScope),
        ]);
      }

      await dbSetMeta(db, `last_sync_${state.userId || "guest"}`, {
        value: data.updated_at || new Date().toISOString(),
        scope: data.scope || "public",
      });
      db.close();
      return true;
    } catch (_error) {
      return false;
    }
  }

  async function applyOfflineFallbackForCurrentPage() {
    if (state.isOnline) return;

    try {
      const db = await withIndexedDB();
      const path = window.location.pathname;
      const userScope = state.userId ? `${state.userId}` : null;
      let hasData = true;

      if (path.startsWith("/products") || path.startsWith("/categories") || path === "/") {
        const categoriesCount = await getStoreCount(db, STORES.categories, "public");
        const productsCount = await getStoreCount(db, STORES.products, "public");
        hasData = categoriesCount > 0 || productsCount > 0;
      } else if (path.startsWith("/orders")) {
        const ordersCount = await getStoreCount(db, STORES.orders, userScope);
        hasData = ordersCount > 0;
      } else if (path.startsWith("/notifications")) {
        const notificationCount = await getStoreCount(db, STORES.notifications, userScope);
        hasData = notificationCount > 0;
      }

      db.close();
      if (!hasData) showNoDataMessage();
    } catch (_error) {
      showNoDataMessage();
    }
  }

  function blockOfflineWrites() {
    document.addEventListener("submit", (event) => {
      if (state.isOnline) return;
      const form = event.target.closest("form");
      if (!form || String(form.method).toLowerCase() !== "post") return;
      event.preventDefault();
      notifyOfflineActionBlocked();
    }, true);
  }

  function bindLogoutHooks() {
    document.querySelectorAll('a[href$="/logout/"]').forEach((link) => {
      link.addEventListener("click", () => {
        if (state.isAuthenticated) {
          clearPrivateUserData();
        } else {
          clearAllPublicCache();
        }
      });
    });
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/static/service-worker.js").catch(() => {});
  }

  function bindConnectivity() {
    window.addEventListener("online", async () => {
      state.isOnline = true;
      state.userId = document.body?.dataset?.userId || null;
      showOfflineBanner(true);
      clearNoDataMessage();
      const synced = await syncNow();
      if (synced) {
        const banner = document.getElementById("offline-status-banner");
        if (banner) {
          banner.textContent = i18n.synced || "Synchronisation terminée.";
          banner.hidden = false;
          banner.classList.add("online");
          banner.classList.remove("d-none");
          setTimeout(() => { banner.hidden = true; }, 2500);
        }
      }
    });

    window.addEventListener("offline", () => {
      state.isOnline = false;
      showOfflineBanner(false);
      applyOfflineFallbackForCurrentPage();
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    registerServiceWorker();
    bindConnectivity();
    blockOfflineWrites();
    bindLogoutHooks();
    showOfflineBanner(navigator.onLine);

    if (navigator.onLine) {
      await syncNow();
    } else {
      await applyOfflineFallbackForCurrentPage();
    }
  });
})();

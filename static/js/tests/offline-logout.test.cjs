const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function harness(abortTransaction = false) {
  const online = true;
  const listeners = {};
  let opening;
  let submitted = 0;
  let closed = false;
  const rows = Object.fromEntries(["orders", "notifications", "seller_orders"].map(name => [name, [{id: 1, scopeKey: "7"}, {id: 2, scopeKey: "8"}]]));
  const form = { method: "post", addEventListener: (name, callback) => { listeners[name] = callback; } };
  const document = {
    body: { dataset: { userId: "7", userAuthenticated: "1" } },
    getElementById: () => null,
    querySelectorAll: selector => selector.startsWith("form") ? [form] : [],
    addEventListener: (name, callback) => { if (name === "DOMContentLoaded") listeners.ready = callback; },
  };
  const db = {
    objectStoreNames: { contains: name => name in rows },
    close: () => { closed = true; },
    transaction(name) {
      const tx = {};
      tx.objectStore = () => ({
        delete: id => { rows[name] = rows[name].filter(row => row.id !== id); },
        openCursor() {
          const request = {};
          if (abortTransaction) {
            queueMicrotask(() => { tx.error = new Error("Transaction aborted"); tx.onabort(); });
            return request;
          }
          const snapshot = [...rows[name]];
          let index = 0;
          function next() {
            queueMicrotask(() => {
              const row = snapshot[index++];
              request.result = row ? { value: row, key: row.id, continue: next } : null;
              request.onsuccess();
              if (!row) tx.oncomplete();
            });
          }
          next();
          return request;
        },
      });
      return tx;
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../offline-manager.js"), "utf8"), {
    document,
    navigator: { onLine: online },
    window: { addEventListener() {}, location: { pathname: "/" } },
    indexedDB: { open: () => { opening = {}; return opening; } },
    fetch: async () => ({ ok: false }),
    HTMLFormElement: { prototype: { submit() { submitted++; } } },
    console,
  });
  return {
    rows, listeners,
    ready: () => listeners.ready(),
    submit: (defaultPrevented = false) => listeners.submit({ defaultPrevented, preventDefault() {} }),
    finish: () => { opening.result = db; opening.onsuccess(); },
    fail: () => { opening.error = new Error("IndexedDB unavailable"); opening.onerror(); },
    submitted: () => submitted,
    closed: () => closed,
  };
}

test("logout waits for current user's private purge before native POST", async () => {
  const app = harness();
  await app.ready();
  assert.equal(typeof app.listeners.submit, "function");
  const pending = app.submit();
  assert.equal(app.submitted(), 0);
  app.finish();
  await pending;
  assert.equal(app.submitted(), 1);
  assert.equal(app.closed(), true);
  for (const rows of Object.values(app.rows)) assert.deepEqual(rows, [{id: 2, scopeKey: "8"}]);
});

test("IndexedDB error cannot prevent server logout", async () => {
  const app = harness();
  await app.ready();
  const pending = app.submit();
  app.fail();
  await pending;
  assert.equal(app.submitted(), 1);
});

test("duplicate submissions share a single logout", async () => {
  const app = harness();
  await app.ready();
  const pending = app.submit();
  await app.submit();
  app.finish();
  await pending;
  assert.equal(app.submitted(), 1);
});

test("transaction abort closes storage and still ends server session", async () => {
  const app = harness(true);
  await app.ready();
  const pending = app.submit();
  app.finish();
  await pending;
  assert.equal(app.closed(), true);
  assert.equal(app.submitted(), 1);
});

test("offline write cancellation is respected while private data is cleared", async () => {
  const app = harness();
  await app.ready();
  const pending = app.submit(true);
  app.finish();
  await pending;
  assert.equal(app.submitted(), 0);
  for (const rows of Object.values(app.rows)) assert.deepEqual(rows, [{id: 2, scopeKey: "8"}]);
});

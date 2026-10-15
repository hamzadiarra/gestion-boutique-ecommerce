const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness({offline = false} = {}) {
  const listeners = {}, puts = [], calls = [], deleted = [];
  const anonymous = new Response('anonymous shell');
  const cache = {match: async () => anonymous.clone(), addAll: async urls => assert.ok(!urls.includes('/')), put: async (key, response) => puts.push([key, await response.text()])};
  class LocalRequest extends Request { constructor(url, options) { super(new URL(url, 'https://shop.test'), options); } }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../service-worker.js'), 'utf8'), {
    self: {addEventListener: (name, callback) => listeners[name] = callback, skipWaiting() {}, clients: {claim: async () => {}}},
    location: {origin: 'https://shop.test'}, URL, Request: LocalRequest, Response,
    caches: {open: async () => cache, match: async () => { throw Error('cross-cache lookup forbidden'); }, keys: async () => ['gestion-boutique-shell-v4-corrections','unrelated-app'], delete: async key => deleted.push(key)},
    fetch: async (request, options) => { calls.push([request, options]); if (offline) throw Error('offline'); return new Response(request.credentials === 'omit' ? 'anonymous shell' : 'private account data'); },
  });
  async function dispatch(name, request) {
    let pending;
    listeners[name]({request, waitUntil: promise => pending = promise, respondWith: promise => pending = promise});
    return pending;
  }
  return {dispatch, puts, calls, deleted};
}

test('install caches only an explicitly anonymous HTML shell', async () => {
  const h = harness(); await h.dispatch('install');
  assert.equal(h.calls[0][0].credentials, 'omit');
  assert.deepEqual(h.puts, [['/', 'anonymous shell']]);
});
test('activation removes legacy app caches without deleting other apps', async () => {
  const h = harness(); await h.dispatch('activate');
  assert.deepEqual(h.deleted, ['gestion-boutique-shell-v4-corrections']);
});
test('private routes and synchronization never enter Cache Storage', async () => {
  for (const route of ['/offline/sync/', '/accounts/profile/', '/cart/', '/payments/1/', '/dashboard/', '/dashboard/comptable/', '/dashboard/comptable/clotures/', '/orders/1/', '/notifications/']) {
    const h = harness(); const response = await h.dispatch('fetch', new Request('https://shop.test'+route));
    assert.equal(await response.text(), 'private account data');
    assert.equal(h.puts.length, 0); assert.equal(h.calls[0][1].cache, 'no-store');
    const offline = harness({offline: true});
    const denied = await offline.dispatch('fetch', new Request('https://shop.test'+route));
    assert.equal(denied.status, 503); assert.equal(denied.headers.get('Cache-Control'), 'no-store');
  }
});
test('public HTML is not cached with personalized navigation', async () => {
  const h = harness();
  const request = new Request('https://shop.test/products/', {headers: {accept: 'text/html'}});
  const response = await h.dispatch('fetch', request);
  assert.equal(await response.text(), 'private account data'); assert.equal(h.puts.length, 0);
  const offline = harness({offline: true});
  assert.equal(await (await offline.dispatch('fetch', request)).text(), 'anonymous shell');
});

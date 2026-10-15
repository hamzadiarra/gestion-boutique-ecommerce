const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

// Only browser and network boundaries are simulated; each test runs assistant.js.
function harness(lang = 'fr') {
    let document;
    class Element {
        constructor(tag = 'div', className = '') {
            Object.assign(this, { tagName: tag.toUpperCase(), className, children: [], dataset: {}, attributes: {}, listeners: {}, hidden: false, disabled: false, value: '', _text: '' });
        }
        set textContent(value) { this._text = String(value); this.children = []; }
        get textContent() { return this._text + this.children.map(child => child.textContent).join(' '); }
        get firstElementChild() { return this.children[0]; }
        appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
        remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this); }
        replaceChildren(...children) { this.children = []; this._text = ''; children.forEach(child => this.appendChild(child)); }
        setAttribute(key, value) { this.attributes[key] = String(value); }
        getAttribute(key) { return this.attributes[key] ?? null; }
        addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
        emit(name, extra = {}) {
            const event = { target: this, preventDefault() {}, ...extra };
            (this.listeners[name] || []).forEach(callback => callback(event));
            if (this.parentElement) this.parentElement.emit(name, event);
        }
        click() { if (!this.disabled) this.emit('click'); }
        focus() { document.activeElement = this; }
        requestSubmit() { this.emit('submit'); }
        contains(other) { return other === this || this.children.some(child => child.contains(other)); }
        matches(selector) {
            if (selector.startsWith('.')) return this.className.split(' ').includes(selector.slice(1));
            if (selector === '[data-assistant-question]') return 'assistantQuestion' in this.dataset;
            if (selector === 'input[name="csrfmiddlewaretoken"]') return this.name === 'csrfmiddlewaretoken';
            if (selector === 'button[type="submit"]') return this.tagName === 'BUTTON' && this.type === 'submit';
            return this.tagName.toLowerCase() === selector;
        }
        querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
        querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    }
    const root = new Element();
    const toggle = root.appendChild(new Element('button'));
    const panel = root.appendChild(new Element()); panel.hidden = true;
    const close = panel.appendChild(new Element('button', 'shop-assistant-close'));
    const messages = panel.appendChild(new Element('div', 'shop-assistant-messages'));
    const greeting = messages.appendChild(new Element('p', 'shop-assistant-message assistant-message')); greeting.textContent = 'Welcome';
    const suggestions = panel.appendChild(new Element('div', 'shop-assistant-suggestions'));
    const suggestion = suggestions.appendChild(new Element('button')); suggestion.dataset.assistantQuestion = 'Comment acheter ?';
    const status = panel.appendChild(new Element()); status.hidden = true;
    const form = panel.appendChild(new Element('form'));
    const token = form.appendChild(new Element('input')); token.name = 'csrfmiddlewaretoken'; token.value = 'form-token';
    const input = form.appendChild(new Element('input'));
    const submit = form.appendChild(new Element('button')); submit.type = 'submit';
    const ids = { shopAssistant: root, shopAssistantToggle: toggle, shopAssistantPanel: panel, shopAssistantForm: form, shopAssistantInput: input, shopAssistantStatus: status };
    document = { documentElement: { lang }, cookie: 'csrftoken=fresh-token', activeElement: null, createElement: tag => new Element(tag), getElementById: id => ids[id] };
    const location = new URL('https://shop.test/en/products/12/?secret=omitted');
    root.dataset.endpoint = '/en/assistant/ask/';
    const requests = [];
    const timers = new Map(); let timerId = 0;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../assistant.js'), 'utf8'), {
        document, window: { location, crypto: webcrypto }, location, crypto: webcrypto, URL, Intl, AbortController, console,
        setTimeout(callback) { timers.set(++timerId, callback); return timerId; }, clearTimeout(id) { timers.delete(id); },
        fetch(url, options) { return new Promise((resolve, reject) => { requests.push({ url, options, resolve, reject }); }); },
    });
    return { root, toggle, panel, close, messages, suggestions, suggestion, status, form, input, submit, document, requests,
        send(message) { input.value = message; form.requestSubmit(); },
        respond(data = { answer: 'Réponse', results: [], actions: [], suggestions: [] }, code = 200) { requests.at(-1).resolve({ ok: code >= 200 && code < 300, status: code, json: async () => data }); },
        timeout() { [...timers.values()].forEach(callback => callback()); },
    };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('sends page context, a UUID and current CSRF cookie with same-origin credentials', () => {
    const app = harness(); app.send(' Mon panier ');
    const request = app.requests[0];
    const payload = JSON.parse(request.options.body);
    assert.equal(payload.message, 'Mon panier');
    assert.equal(payload.context, '/en/products/12/');
    assert.match(payload.request_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    assert.equal(request.options.credentials, 'same-origin');
    assert.equal(request.options.headers['X-CSRFToken'], 'fresh-token');
});

test('one pending request disables send and suggestions and shows localized progress', async () => {
    const app = harness('en'); app.send('Hello'); app.send('Another'); app.suggestion.click();
    assert.equal(app.requests.length, 1);
    assert.equal(app.submit.disabled, true);
    assert.equal(app.suggestion.disabled, true);
    assert.equal(app.status.hidden, false);
    assert.match(app.status.textContent, /thinking|searching|working/i);
    app.respond(); await flush();
    assert.equal(app.submit.disabled, false);
    assert.equal(app.status.hidden, true);
    assert.match(app.messages.textContent, /Réponse/);
});

test('network retry restores the draft and reuses ID without duplicating the user turn', async () => {
    const app = harness(); app.send('Mon panier');
    app.requests[0].reject(new TypeError('Network failure')); await flush();
    assert.equal(app.input.value, 'Mon panier');
    assert.equal(app.submit.disabled, false);
    const retry = app.messages.querySelector('button'); assert.ok(retry);
    assert.match(retry.textContent, /Réessayer/);
    retry.click();
    assert.equal(JSON.parse(app.requests[1].options.body).request_id, JSON.parse(app.requests[0].options.body).request_id);
    app.respond(); await flush();
    assert.equal(app.messages.querySelectorAll('.user-message').length, 1);
    assert.equal(app.messages.querySelector('button'), null);
});

test('editing a failed message starts a new request and preserves drafts typed while busy', async () => {
    const app = harness(); app.send('first'); app.input.value = 'new draft';
    app.requests[0].reject(new Error('offline')); await flush();
    assert.equal(app.input.value, 'new draft'); app.form.requestSubmit();
    assert.notEqual(JSON.parse(app.requests[1].options.body).request_id, JSON.parse(app.requests[0].options.body).request_id);
});

test('renders product price/stock and text safely, allowing only local product links and support actions', async () => {
    const app = harness('en'); app.send('phone');
    app.respond({ answer: '<img src=x onerror=alert(1)>', results: [
        { id: 1, name: 'Phone', url: '/en/products/1/', price: '12500.00', currency: 'XOF', stock: 3, available: true },
        { id: 2, name: 'Sold out', url: '/en/products/2/', price: '0.00', currency: 'XOF', stock: 0, available: false },
        { id: 3, name: 'Unsafe product', url: 'https://evil.test/item', price: '1', currency: 'XOF', stock: 1, available: true },
    ], actions: [
        { label: 'Cart', url: '/en/cart/' }, { label: 'Email', url: 'mailto:shop@example.test' },
        { label: 'WhatsApp', url: 'https://api.whatsapp.com/send?phone=22312345678' },
        ...['javascript:alert(1)', 'data:text/html,test', '//evil.test', 'https://api.whatsapp.com.evil.test/send', 'https://api.whatsapp.com/other', 'mailto:x@example.test%0d%0aBcc:evil@example.test'].map(url => ({ label: 'Unsafe', url })),
    ] }); await flush();
    const links = app.messages.querySelectorAll('a');
    assert.equal(links.length, 5);
    assert.match(app.messages.textContent, /Phone/); assert.match(app.messages.textContent, /12[\s,\u00a0\u202f]?500/);
    assert.match(app.messages.textContent, /3.*in stock|in stock.*3/i); assert.match(app.messages.textContent, /out of stock/i);
    assert.match(app.messages.textContent, /<img src=x onerror=alert\(1\)>/);
    assert.equal(app.messages.querySelector('img'), null);
    assert.equal(links.find(link => link.textContent === 'WhatsApp').rel, 'noopener noreferrer');
});

test('server suggestions replace starter questions and send their message, not label', async () => {
    const app = harness(); app.send('help');
    app.respond({ answer: 'Choose', suggestions: [{ label: 'My basket', message: 'Show my cart' }] }); await flush();
    const buttons = app.suggestions.querySelectorAll('button'); assert.equal(buttons.length, 1);
    assert.equal(buttons[0].textContent, 'My basket'); buttons[0].click();
    assert.equal(JSON.parse(app.requests[1].options.body).message, 'Show my cart');
});

test('Escape closes the panel and returns keyboard focus to its launcher', () => {
    const app = harness(); app.toggle.click(); assert.equal(app.document.activeElement, app.input);
    app.input.emit('keydown', { key: 'Escape' });
    assert.equal(app.panel.hidden, true); assert.equal(app.document.activeElement, app.toggle);
    assert.equal(app.toggle.getAttribute('aria-expanded'), 'false');
});

test('choosing a suggestion keeps keyboard focus in the input when suggestions are replaced', async () => {
    const app = harness(); app.toggle.click(); app.suggestion.focus(); app.suggestion.click();
    app.respond({ answer: 'Choose again', suggestions: [{ label: 'Basket', message: 'My basket' }] }); await flush();
    assert.equal(app.document.activeElement, app.input);
});

test('malformed responses remain retryable and CSRF falls back to the rendered token', async () => {
    const app = harness(); app.document.cookie = 'csrftoken=%broken'; app.send('help');
    assert.equal(app.requests[0].options.headers['X-CSRFToken'], 'form-token');
    app.requests[0].resolve({ ok: true, status: 200, json: async () => { throw new SyntaxError('HTML response'); } }); await flush();
    assert.equal(app.input.value, 'help'); assert.equal(app.submit.disabled, false);
    assert.ok(app.messages.querySelector('button'));
    assert.doesNotMatch(app.messages.textContent, /HTML response/);
});

test('timeouts recover the form and late responses cannot overwrite a retry', async () => {
    const app = harness('en'); app.send('slow'); const first = app.requests[0];
    app.timeout(); await flush();
    assert.equal(first.options.signal.aborted, true); assert.equal(app.submit.disabled, false);
    app.form.requestSubmit(); app.respond({ answer: 'Fresh response' }); await flush();
    first.resolve({ ok: true, status: 200, json: async () => ({ answer: 'Stale response' }) }); await flush();
    assert.match(app.messages.textContent, /Fresh response/); assert.doesNotMatch(app.messages.textContent, /Stale response/);
});

test('HTTP errors explain rate limits and recover controls in both languages', async () => {
    for (const [lang, code, expected] of [['en', 429, /too many|wait/i], ['fr', 429, /attend|demandes/i], ['en', 409, /progress|wait/i], ['fr', 413, /long|500/i]]) {
        const app = harness(lang); app.send('help'); app.respond({ error: 'Internal details should not leak' }, code); await flush();
        assert.match(app.messages.textContent, expected);
        assert.doesNotMatch(app.messages.textContent, /Internal details/);
        assert.equal(app.submit.disabled, false);
    }
});

test('history keeps at most twenty user turns', async () => {
    const app = harness();
    for (let i = 0; i < 25; i++) { app.send('question ' + i); app.respond({ answer: 'answer ' + i }); await flush(); }
    assert.equal(app.messages.querySelectorAll('.user-message').length, 20);
    assert.doesNotMatch(app.messages.textContent, /question 0\b/);
    assert.match(app.messages.textContent, /answer 24/);
});

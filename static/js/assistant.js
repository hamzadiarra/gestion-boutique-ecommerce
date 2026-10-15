(function () {
    const root = document.getElementById('shopAssistant');
    if (!root) return;
    const toggle = document.getElementById('shopAssistantToggle');
    const panel = document.getElementById('shopAssistantPanel');
    const close = root.querySelector('.shop-assistant-close');
    const form = document.getElementById('shopAssistantForm');
    const input = document.getElementById('shopAssistantInput');
    const messages = root.querySelector('.shop-assistant-messages');
    const suggestions = root.querySelector('.shop-assistant-suggestions');
    const status = document.getElementById('shopAssistantStatus');
    const submit = form.querySelector('button[type="submit"]');
    const english = document.documentElement.lang.toLowerCase().startsWith('en');
    const turns = [];
    let busy = false;
    let failedRequest = null;

    function translated(fr, en) { return english ? en : fr; }
    function getCsrfToken() {
        // Le cookie est prioritaire : Django peut renouveler le secret après
        // une connexion, alors que le formulaire déjà rendu peut être ancien.
        const cookie = document.cookie.split(';').map(function (part) { return part.trim(); }).find(function (part) { return part.indexOf('csrftoken=') === 0; });
        if (cookie) {
            try { return decodeURIComponent(cookie.substring('csrftoken='.length)); } catch (_) { /* Fall back to the rendered token. */ }
        }
        const input = root.querySelector('input[name="csrfmiddlewaretoken"]');
        return input && input.value ? input.value : null;
    }
    function setOpen(open) {
        panel.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        (open ? input : toggle).focus();
    }
    function setBusy(value) {
        busy = value;
        submit.disabled = value;
        form.setAttribute('aria-busy', String(value));
        root.querySelectorAll('[data-assistant-question]').forEach(function (button) { button.disabled = value; });
        if (status) {
            status.hidden = !value;
            status.textContent = value ? translated('Je cherche une réponse…', 'Searching for an answer…') : '';
        }
    }
    function addMessage(parent, text, type) {
        const item = document.createElement('p');
        item.className = 'shop-assistant-message ' + type;
        item.textContent = text;
        parent.appendChild(item);
        return item;
    }
    function safeUrl(value, support) {
        if (typeof value !== 'string' || !value || /[\u0000-\u0020\u007f\\]|%0[ad]/i.test(value)) return null;
        try {
            const url = new URL(value, window.location.href);
            if (url.username || url.password) return null;
            if ((url.protocol === 'https:' || url.protocol === 'http:') && url.origin === window.location.origin) {
                return url.pathname + url.search + url.hash;
            }
            if (support && url.protocol === 'mailto:' && /^mailto:[^?&#\s]+@[^?&#\s]+$/i.test(value)) return url.href;
            if (support && url.protocol === 'https:' && url.host === 'api.whatsapp.com' && url.pathname === '/send') return url.href;
        } catch (_) { /* Invalid URLs are omitted. */ }
        return null;
    }
    function addActions(parent, actions) {
        if (!Array.isArray(actions)) return;
        const list = document.createElement('div');
        list.className = 'shop-assistant-actions';
        actions.slice(0, 8).forEach(function (action) {
            if (!action || typeof action.label !== 'string') return;
            const url = safeUrl(action.url, true);
            if (!url) return;
            const link = document.createElement('a');
            link.href = url;
            link.rel = 'noopener noreferrer';
            link.textContent = action.label;
            list.appendChild(link);
        });
        if (list.children.length) parent.appendChild(list);
    }
    function addResults(parent, results) {
        if (!Array.isArray(results)) return;
        const list = document.createElement('div');
        list.className = 'shop-assistant-results';
        results.slice(0, 8).forEach(function (result) {
            if (!result || typeof result.name !== 'string') return;
            const url = safeUrl(result.url, false);
            if (!url) return;
            const link = document.createElement('a');
            link.href = url;
            const name = document.createElement('strong');
            name.textContent = result.name;
            link.appendChild(name);
            const details = [];
            if (result.currency === 'XOF' && typeof result.price === 'string' && /^\d+(\.\d{1,2})?$/.test(result.price) && Number.isFinite(Number(result.price))) {
                details.push(new Intl.NumberFormat(english ? 'en' : 'fr', { style: 'currency', currency: 'XOF', maximumFractionDigits: 2 }).format(Number(result.price)));
            }
            if (Number.isInteger(result.stock) && result.stock >= 0) {
                details.push(result.available === false || result.stock === 0
                    ? translated('Rupture de stock', 'Out of stock')
                    : result.stock + translated(' en stock', ' in stock'));
            }
            if (details.length) {
                const detail = document.createElement('span');
                detail.textContent = details.join(' · ');
                link.appendChild(detail);
            }
            list.appendChild(link);
        });
        if (list.children.length) parent.appendChild(list);
    }
    function bindSuggestion(button) {
        button.addEventListener('click', function () {
            if (busy) return;
            input.value = button.dataset.assistantQuestion;
            if (!panel.hidden) input.focus();
            form.requestSubmit();
        });
    }
    function updateSuggestions(items) {
        if (!suggestions || !Array.isArray(items)) return;
        suggestions.replaceChildren();
        items.slice(0, 6).forEach(function (item) {
            if (!item || typeof item.label !== 'string' || typeof item.message !== 'string' || !item.message.trim() || item.message.length > 500) return;
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = item.label;
            button.dataset.assistantQuestion = item.message;
            button.disabled = busy;
            bindSuggestion(button);
            suggestions.appendChild(button);
        });
    }
    function requestId() {
        if (window.crypto.randomUUID) return window.crypto.randomUUID();
        const bytes = window.crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        const hex = Array.from(bytes, function (byte) { return byte.toString(16).padStart(2, '0'); }).join('');
        return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
    }
    function errorMessage(error) {
        if (error.status === 429) return translated('Trop de demandes. Patientez un instant avant de réessayer.', 'Too many requests. Please wait a moment before retrying.');
        if (error.status === 409) return translated('Une demande est déjà en cours. Patientez puis réessayez.', 'A request is already in progress. Please wait and retry.');
        if (error.status === 413) return translated('Votre question est trop longue. Limitez-la à 500 caractères.', 'Your question is too long. Please use at most 500 characters.');
        if (error.status === 403) return translated('Veuillez actualiser la page avant de réessayer.', 'Please refresh the page before trying again.');
        return translated('La réponse n’a pas pu être reçue. Vérifiez votre connexion puis réessayez.', 'The answer could not be received. Check your connection and retry.');
    }
    async function send(message) {
        if (busy || !message || message.length > 500) return;
        const request = failedRequest && failedRequest.message === message ? failedRequest : { message: message, id: requestId(), context: window.location.pathname };
        if (failedRequest && failedRequest.retry) {
            if (!panel.hidden && document.activeElement === failedRequest.retry) input.focus();
            failedRequest.retry.remove();
        }
        failedRequest = null;
        if (!request.turn) {
            request.turn = document.createElement('div');
            request.turn.className = 'shop-assistant-turn';
            addMessage(request.turn, message, 'user-message');
            messages.appendChild(request.turn);
            turns.push(request.turn);
            if (turns.length > 20) turns.shift().remove();
        }
        if (request.error) request.error.remove();
        input.value = '';
        setBusy(true);
        const controller = new AbortController();
        let timer;
        try {
            // The race also prevents a response arriving after timeout from changing the transcript.
            const data = await Promise.race([
                fetch(root.dataset.endpoint, {
                    method: 'POST', credentials: 'same-origin', signal: controller.signal,
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() || '' },
                    body: JSON.stringify({ message: message, context: request.context, request_id: request.id }),
                }).then(async function (response) {
                    if (!response.ok) throw { status: response.status };
                    const payload = await response.json();
                    if (!payload || typeof payload.answer !== 'string') throw new Error('Invalid response');
                    return payload;
                }),
                new Promise(function (_, reject) {
                    timer = setTimeout(function () { controller.abort(); reject(new Error('Timeout')); }, 15000);
                }),
            ]);
            addMessage(request.turn, data.answer, 'assistant-message');
            addResults(request.turn, data.results);
            addActions(request.turn, data.actions);
            updateSuggestions(data.suggestions);
        } catch (error) {
            failedRequest = request;
            request.error = addMessage(request.turn, errorMessage(error), 'assistant-message');
            request.retry = document.createElement('button');
            request.retry.type = 'button';
            request.retry.className = 'shop-assistant-retry';
            request.retry.textContent = translated('Réessayer', 'Retry');
            request.retry.addEventListener('click', function () { send(request.message); });
            request.turn.appendChild(request.retry);
            if (!input.value) input.value = message;
        } finally {
            clearTimeout(timer);
            setBusy(false);
            messages.scrollTop = messages.scrollHeight;
            if (!panel.hidden && (document.activeElement === submit || document.activeElement === request.retry)) input.focus();
        }
    }
    toggle.addEventListener('click', function () { setOpen(panel.hidden); });
    close.addEventListener('click', function () { setOpen(false); });
    root.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); setOpen(false); }
    });
    root.querySelectorAll('[data-assistant-question]').forEach(bindSuggestion);
    form.addEventListener('submit', function (event) { event.preventDefault(); send(input.value.trim()); });
}());

(function () {
    const root = document.getElementById('shopAssistant');
    if (!root) return;
    const toggle = document.getElementById('shopAssistantToggle');
    const panel = document.getElementById('shopAssistantPanel');
    const close = root.querySelector('.shop-assistant-close');
    const form = document.getElementById('shopAssistantForm');
    const input = document.getElementById('shopAssistantInput');
    const messages = root.querySelector('.shop-assistant-messages');
    function getCsrfToken() {
        // Le cookie est prioritaire : Django peut renouveler le secret après
        // une connexion, alors que le formulaire déjà rendu peut être ancien.
        const cookie = document.cookie.split(';').map(function (part) { return part.trim(); }).find(function (part) { return part.indexOf('csrftoken=') === 0; });
        if (cookie) return decodeURIComponent(cookie.substring('csrftoken='.length));
        const input = root.querySelector('input[name="csrfmiddlewaretoken"]');
        return input && input.value ? input.value : null;
    }
    function setOpen(open) { panel.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); if (open) input.focus(); }
    function addMessage(text, type) { const item = document.createElement('p'); item.className = 'shop-assistant-message ' + type; item.textContent = text; messages.appendChild(item); messages.scrollTop = messages.scrollHeight; }
    function addActions(actions) { if (!actions || !actions.length) return; const list = document.createElement('div'); list.className = 'shop-assistant-actions'; actions.forEach(function (action) { const link = document.createElement('a'); link.href = action.url; link.textContent = action.label; list.appendChild(link); }); messages.appendChild(list); }
    function addResults(results) { if (!results || !results.length) return; const list = document.createElement('div'); list.className = 'shop-assistant-actions'; results.forEach(function (result) { const link = document.createElement('a'); link.href = result.url; link.textContent = result.name; list.appendChild(link); }); messages.appendChild(list); }
    toggle.addEventListener('click', function () { setOpen(panel.hidden); });
    close.addEventListener('click', function () { setOpen(false); });
    root.querySelectorAll('[data-assistant-question]').forEach(function (button) { button.addEventListener('click', function () { input.value = button.dataset.assistantQuestion; form.requestSubmit(); }); });
    form.addEventListener('submit', function (event) { event.preventDefault(); const message = input.value.trim(); if (!message) return; const csrfToken = getCsrfToken(); addMessage(message, 'user-message'); input.value = ''; fetch(root.dataset.endpoint, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken || '' }, body: JSON.stringify({ message: message }) }).then(function (response) { return response.json().then(function (data) { if (!response.ok) throw new Error(data.error || 'Request failed'); return data; }); }).then(function (data) { addMessage(data.answer, 'assistant-message'); addResults(data.results); addActions(data.actions); }).catch(function () { addMessage(document.documentElement.lang === 'en' ? 'The guide is temporarily unavailable.' : 'Le guide est momentanément indisponible.', 'assistant-message'); }); });
}());

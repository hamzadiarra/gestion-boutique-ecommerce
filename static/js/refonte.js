(() => {
  "use strict";
  const english = document.documentElement.lang === "en";
  const header = document.querySelector(".site-header");
  const measureHeader = () => document.documentElement.style.setProperty("--header-height", `${header.getBoundingClientRect().height}px`);
  if (header) { measureHeader(); if (window.ResizeObserver) new ResizeObserver(measureHeader).observe(header); }
  const heroCopy = document.querySelector(".shop-hero-copy");
  if (heroCopy) {
    const measureHero = () => heroCopy.closest(".shop-hero").style.setProperty("--hero-copy-height", `${heroCopy.getBoundingClientRect().height}px`);
    measureHero(); if (window.ResizeObserver) new ResizeObserver(measureHero).observe(heroCopy);
  }
  document.querySelectorAll("[data-history-back]").forEach(link => link.addEventListener("click", event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    try {
      const previous = new URL(document.referrer);
      if (previous.origin === location.origin && previous.href !== location.href && history.length > 1) {
        event.preventDefault(); history.back();
      }
    } catch (_) { /* Le lien reste la destination de secours. */ }
  }));
  document.querySelectorAll('input[type="search"][name="q"]').forEach((input, index) => {
    const host = input.parentElement, form = input.form;
    host.classList.add("autocomplete-host");
    const list = document.createElement("div");
    list.id = `product-suggestions-${index}`; list.className = "product-suggestions";
    list.setAttribute("role", "listbox"); list.hidden = true; host.append(list);
    const status = document.createElement("span");
    status.className = "visually-hidden"; status.setAttribute("role", "status"); host.append(status);
    input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", list.id); input.setAttribute("aria-expanded", "false");
    input.setAttribute("autocomplete", "off");
    if (!input.getAttribute("aria-label")) input.setAttribute("aria-label", english ? "Search products" : "Rechercher des produits");
    let timer, controller, version = 0, selected = -1;
    const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); selected = -1; };
    input.addEventListener("input", () => {
      clearTimeout(timer); controller?.abort(); const current = ++version; close();
      if (input.value.trim().length < 2) return;
      timer = setTimeout(async () => {
        controller = new AbortController();
        const params = new URLSearchParams({q: input.value.trim()});
        const category = form?.elements.namedItem("categorie");
        if (category?.value) params.set("categorie", category.value);
        try {
          const response = await fetch(`${document.body.dataset.searchEndpoint}?${params}`, {signal: controller.signal, cache: "no-store"});
          if (!response.ok) throw new Error("search");
          const data = await response.json();
          if (current !== version || document.activeElement !== input) return;
          list.replaceChildren();
          data.results.forEach((product, i) => {
            const link = document.createElement("a"); link.className = "product-suggestion";
            link.href = product.url; link.id = `${list.id}-${i}`; link.setAttribute("role", "option"); link.setAttribute("aria-selected", "false");
            if (product.image) { const img = document.createElement("img"); img.src = product.image; img.alt = ""; img.loading = "lazy"; link.append(img); }
            const text = document.createElement("span"), name = document.createElement("strong"), info = document.createElement("small");
            name.textContent = product.name;
            info.textContent = `${Number(product.price).toLocaleString(english ? "en" : "fr")} FCFA · ${product.available ? (english ? "In stock" : "En stock") : (english ? "Out of stock" : "Épuisé")}`;
            text.append(name, info); link.append(text); list.append(link);
          });
          status.textContent = english ? `${data.results.length} suggestions` : `${data.results.length} suggestions`;
          if (!data.results.length) { const empty = document.createElement("p"); empty.className = "suggestions-status"; empty.textContent = english ? "No products found. Try another term." : "Aucun produit trouvé. Essayez un autre terme."; list.append(empty); status.textContent = empty.textContent; }
          list.hidden = false; input.setAttribute("aria-expanded", "true");
        } catch (error) { if (error.name !== "AbortError" && current === version) { close(); status.textContent = english ? "Search unavailable. Submit the form to try again." : "Suggestions indisponibles. Validez la recherche pour réessayer."; } }
      }, 250);
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Escape") { version++; controller?.abort(); close(); }
      const links = [...list.querySelectorAll("a")];
      if (list.hidden || !links.length) return;
      if (["ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault(); selected = (selected + (event.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
        links.forEach((link, i) => link.setAttribute("aria-selected", String(i === selected)));
        input.setAttribute("aria-activedescendant", links[selected].id); links[selected].scrollIntoView({block: "nearest"});
      } else if (event.key === "Enter" && selected >= 0) { event.preventDefault(); links[selected].click(); }
    });
    document.addEventListener("click", event => { if (!host.contains(event.target)) close(); });
    host.addEventListener("focusout", () => setTimeout(() => { if (!host.contains(document.activeElement)) close(); }, 0));
  });
  document.querySelectorAll('.shop-filter-panel select[name="categorie"]').forEach(select => select.addEventListener("change", () => {
    select.form.elements.prix_min.value = ""; select.form.elements.prix_max.value = "";
    select.form.elements.disponibilite.value = ""; select.form.requestSubmit();
  }));
})();

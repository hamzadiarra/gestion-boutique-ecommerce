(() => {
  "use strict";
  const script = document.querySelector("script[data-offers-url]");
  const select = document.getElementById("courier-offer"), quote = document.getElementById("delivery-quote");
  const status = document.getElementById("offer-status"), city = document.getElementById("ville");
  const form = document.getElementById("checkout-form");
  let sequence = 0;
  function mode() { return form.querySelector('[name="mode_livraison"]:checked').value; }
  function displayFee() {
    const fee = select.value ? Number(select.selectedOptions[0].dataset.fee) : (mode() === "express" ? 2500 : 0);
    document.getElementById("checkout-fee").textContent = fee.toLocaleString("fr-FR") + " FCFA";
    document.getElementById("checkout-total").textContent = (Number(script.dataset.subtotal)+fee).toLocaleString("fr-FR") + " FCFA";
  }
  function clear() {
    sequence++; select.replaceChildren(new Option("Tarif habituel de la boutique", "")); quote.value = "";
    status.textContent = "Tarif habituel sélectionné. Consultez les offres pour choisir un tarif personnalisé."; displayFee();
  }
  city.addEventListener("input", clear);
  form.querySelectorAll('[name="mode_livraison"]').forEach(input => input.addEventListener("change", clear));
  document.getElementById("refresh-offers").addEventListener("click", async () => {
    clear(); const requestId = sequence;
    status.textContent = "Recherche des offres approuvées…";
    try {
      const url = new URL(script.dataset.offersUrl, location.origin);
      url.searchParams.set("mode", mode()); url.searchParams.set("ville", city.value);
      const response = await fetch(url, {credentials:"same-origin", cache:"no-store"});
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (requestId !== sequence) return;
      data.offres.forEach(offer => { const option = new Option(offer.label, offer.id); option.dataset.quote = offer.devis; option.dataset.fee = offer.montant; select.add(option); });
      status.textContent = data.offres.length ? "Choisissez une offre. Le devis est valable 30 minutes." : "Aucune offre personnalisée pour cette ville et ce mode.";
    } catch (_) { if (requestId === sequence) status.textContent = "Offres indisponibles. Vérifiez votre ville et réessayez. Le tarif habituel reste disponible."; }
  });
  select.addEventListener("change", () => { quote.value = select.selectedOptions[0].dataset.quote || ""; displayFee(); });
})();

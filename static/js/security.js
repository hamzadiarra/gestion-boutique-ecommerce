(() => {
  const select = document.getElementById("security-event");
  select.addEventListener("change", () => { document.getElementById("security-user").value = select.selectedOptions[0]?.dataset.user || ""; });
  const button = document.getElementById("security-refresh");
  let enabled = true, dirty = false;
  document.querySelectorAll("form").forEach(form => form.addEventListener("input", () => { dirty = true; }));
  button.addEventListener("click", () => { enabled = !enabled; button.setAttribute("aria-pressed", String(enabled)); button.textContent = enabled ? "Actualisation : 30 s" : "Actualisation en pause"; });
  setInterval(() => { if (enabled && !dirty && !document.hidden && !document.activeElement.closest("form")) location.reload(); }, 30000);
})();

(() => {
  const select = document.getElementById("security-event");
  const user = document.getElementById("security-user");
  if (select && user) {
    const syncUser = () => { user.value = select.selectedOptions[0]?.dataset.user || ""; };
    select.addEventListener("change", syncUser);
    syncUser();
  }
  const button = document.getElementById("security-refresh");
  if (!button) return;
  let enabled = true, dirty = false;
  const updateButton = () => {
    button.setAttribute("aria-pressed", String(enabled));
    button.textContent = dirty ? "Pause : formulaire en cours" : (enabled ? "Actualisation : 30 s" : "Actualisation en pause");
  };
  document.querySelectorAll("form[data-security-form]").forEach(form => {
    const preserveDraft = () => { dirty = true; updateButton(); };
    form.addEventListener("input", preserveDraft);
    form.addEventListener("change", preserveDraft);
  });
  button.addEventListener("click", () => { enabled = !enabled; updateButton(); });
  setInterval(() => {
    if (enabled && !dirty && !document.hidden && !document.activeElement?.closest("form")) location.reload();
  }, 30000);
})();

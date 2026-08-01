/**
 * Gestion Boutique E-commerce — Animations & Dark Mode JS
 */

document.addEventListener("DOMContentLoaded", function () {
  // ==========================================
  // GESTION DU MODE SOMBRE / CLAIR (DARK MODE)
  // ==========================================
  const toggleButtons = document.querySelectorAll(".dark-mode-toggle");
  const htmlElement = document.documentElement;

  // Appliquer le thème sauvegardé ou par défaut (light)
  const savedTheme = localStorage.getItem("theme") || "light";
  setTheme(savedTheme);

  toggleButtons.forEach(btn => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const currentTheme = htmlElement.getAttribute("data-theme") || "light";
      const newTheme = currentTheme === "dark" ? "light" : "dark";
      setTheme(newTheme);
    });
  });

  function setTheme(theme) {
    htmlElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);

    // Mettre à jour tous les icônes et textes des boutons de thème
    document.querySelectorAll(".dark-mode-toggle").forEach(btn => {
      const icon = btn.querySelector(".theme-icon") || btn.querySelector("i") || btn;
      const label = btn.querySelector(".theme-label");

      if (theme === "dark") {
        if (icon && icon.tagName === 'I') {
          icon.className = "bi bi-sun-fill text-warning theme-icon";
        }
        if (label) label.textContent = "Mode Clair";
      } else {
        if (icon && icon.tagName === 'I') {
          icon.className = "bi bi-moon-stars-fill theme-icon";
        }
        if (label) label.textContent = "Mode Sombre";
      }
    });
  }

  // ==========================================
  // PARTICULES FLOTTANTES EN ARRIÈRE-PLAN
  // ==========================================
  const particlesContainer = document.getElementById("particles-container");
  if (particlesContainer) {
    const particleCount = 12;
    for (let i = 0; i < particleCount; i++) {
      createParticle(particlesContainer);
    }
  }

  function createParticle(container) {
    const particle = document.createElement("div");
    particle.className = "particle";

    const size = Math.random() * 8 + 4; // 4px à 12px
    const left = Math.random() * 100; // 0% à 100%
    const duration = Math.random() * 15 + 10; // 10s à 25s
    const delay = Math.random() * 5;

    particle.style.width = `${size}px`;
    particle.style.height = `${size}px`;
    particle.style.left = `${left}%`;
    particle.style.bottom = "-20px";
    particle.style.animationDuration = `${duration}s`;
    particle.style.animationDelay = `${delay}s`;

    container.appendChild(particle);
  }
});

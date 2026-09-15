/**
 * Gestion Boutique E-commerce — Animations & Dark Mode JS
 */

const htmlElement = document.documentElement;
const themeToggle = document.getElementById("darkModeToggle");

function applyTheme(theme) {
  const safeTheme = theme === "dark" ? "dark" : "light";
  htmlElement.setAttribute("data-theme", safeTheme);
  htmlElement.setAttribute("data-bs-theme", safeTheme);
  try { localStorage.setItem("theme", safeTheme); } catch (error) { /* storage unavailable */ }
  if (themeToggle) {
    const icon = document.getElementById("darkModeIcon");
    if (icon) icon.className = safeTheme === "dark" ? "bi bi-sun-fill theme-icon" : "bi bi-moon-stars-fill theme-icon";
    const action = safeTheme === "dark" ? (themeToggle.dataset.themeLight || "Revenir au thème clair") : (themeToggle.dataset.themeDark || "Passer au thème sombre");
    themeToggle.setAttribute("aria-label", action);
    themeToggle.setAttribute("title", action);
  }
}

let savedTheme = "light";
try {
  savedTheme = localStorage.getItem("theme") || "light";
} catch (error) {
  savedTheme = "light";
}
applyTheme(savedTheme);

if (themeToggle) {
  themeToggle.addEventListener("click", function (event) {
    event.preventDefault();
    const currentTheme = htmlElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
  });
}

document.addEventListener("DOMContentLoaded", function () {

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

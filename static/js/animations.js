/**
 * Gestion Boutique E-commerce — Animations & Dark Mode JS
 */

const htmlElement = document.documentElement;
const themeToggle = document.getElementById("darkModeToggle");
const themeDebugPanel = document.getElementById("theme-debug-panel");

console.log("theme script loaded");
console.log("toggle", themeToggle);

function updateThemeDebug() {
  const isLocalDevelopment = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  if (!themeDebugPanel || !isLocalDevelopment) return;
  const debugIcon = document.getElementById("darkModeIcon");
  const debugValues = {
    "data-theme": htmlElement.getAttribute("data-theme") || "—",
    "data-bs-theme": htmlElement.getAttribute("data-bs-theme") || "—",
    storage: (() => {
      try { return localStorage.getItem("theme") || "null"; } catch (error) { return "indisponible"; }
    })(),
    toggle: themeToggle ? "oui" : "non",
    icon: debugIcon ? "oui" : "non"
  };
  Object.entries(debugValues).forEach(([key, value]) => {
    const target = themeDebugPanel.querySelector(`[data-theme-debug="${key}"]`);
    if (target) target.textContent = value;
  });
  themeDebugPanel.hidden = false;
}

function applyTheme(theme) {
  const safeTheme = theme === "dark" ? "dark" : "light";
  htmlElement.setAttribute("data-theme", safeTheme);
  htmlElement.setAttribute("data-bs-theme", safeTheme);
  try { localStorage.setItem("theme", safeTheme); } catch (error) { /* storage unavailable */ }
  if (themeToggle) {
    const icon = document.getElementById("darkModeIcon");
    if (icon) icon.className = safeTheme === "dark" ? "bi bi-sun-fill theme-icon" : "bi bi-moon-stars-fill theme-icon";
    const action = safeTheme === "dark" ? "Revenir au thème clair" : "Passer au thème sombre";
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
updateThemeDebug();

if (themeToggle) {
  console.log("theme listener attached", themeToggle);
  themeToggle.addEventListener("click", function (event) {
    event.preventDefault();
    const currentTheme = htmlElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    updateThemeDebug();
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

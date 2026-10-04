/**
 * Gestion Boutique E-commerce — Animations & Interactions JS
 * Premium edition — scroll animations, counters, toasts, parallax
 */

document.addEventListener("DOMContentLoaded", function () {

  // ==========================================
  // 1. DARK MODE TOGGLE
  // ==========================================
  const toggleButtons = document.querySelectorAll(".dark-mode-toggle");
  const htmlElement = document.documentElement;

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
  // 2. SCROLL ANIMATIONS (IntersectionObserver)
  // ==========================================
  const animatedElements = document.querySelectorAll(
    '.scroll-animate, .scroll-animate-left, .scroll-animate-right, .scroll-animate-scale'
  );

  if (animatedElements.length > 0) {
    const scrollObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('animate-in');
          scrollObserver.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -40px 0px'
    });

    animatedElements.forEach(el => scrollObserver.observe(el));
  }


  // ==========================================
  // 3. ANIMATED COUNTERS (countUp)
  // ==========================================
  const counterElements = document.querySelectorAll('[data-count-to]');

  if (counterElements.length > 0) {
    const counterObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          counterObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.3 });

    counterElements.forEach(el => counterObserver.observe(el));
  }

  function animateCounter(element) {
    const target = parseInt(element.getAttribute('data-count-to'), 10);
    const suffix = element.getAttribute('data-count-suffix') || '';
    const prefix = element.getAttribute('data-count-prefix') || '';
    const duration = parseInt(element.getAttribute('data-count-duration'), 10) || 2000;
    const start = 0;
    const startTime = performance.now();

    function easeOutCubic(t) {
      return 1 - Math.pow(1 - t, 3);
    }

    function update(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easedProgress = easeOutCubic(progress);
      const currentValue = Math.round(start + (target - start) * easedProgress);

      element.textContent = prefix + currentValue.toLocaleString('fr-FR') + suffix;

      if (progress < 1) {
        requestAnimationFrame(update);
      }
    }

    requestAnimationFrame(update);
  }


  // ==========================================
  // 4. SCROLL TO TOP BUTTON
  // ==========================================
  const scrollToTopBtn = document.getElementById('scrollToTop');

  if (scrollToTopBtn) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 400) {
        scrollToTopBtn.classList.add('visible');
      } else {
        scrollToTopBtn.classList.remove('visible');
      }
    }, { passive: true });

    scrollToTopBtn.addEventListener('click', (e) => {
      e.preventDefault();
      window.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
    });
  }


  // ==========================================
  // 5. AUTO-DISMISS ALERTS → TOAST SYSTEM
  // ==========================================
  // Convert Django messages to premium toasts
  const djangoAlerts = document.querySelectorAll('.django-message-data');
  const toastContainer = document.getElementById('toastContainer');

  if (djangoAlerts.length > 0 && toastContainer) {
    djangoAlerts.forEach((msgEl, index) => {
      const tag = msgEl.getAttribute('data-tag') || 'info';
      const text = msgEl.getAttribute('data-message') || '';

      setTimeout(() => {
        createToast(tag, text);
      }, index * 200);
    });
  }

  function createToast(type, message) {
    if (!toastContainer) return;

    const iconMap = {
      success: 'bi-check-circle-fill text-success',
      error: 'bi-exclamation-triangle-fill text-danger',
      danger: 'bi-exclamation-triangle-fill text-danger',
      warning: 'bi-exclamation-circle-fill text-warning',
      info: 'bi-info-circle-fill text-info',
    };

    const toast = document.createElement('div');
    toast.className = `toast-custom toast-${type}`;
    toast.innerHTML = `
      <i class="bi ${iconMap[type] || iconMap.info} toast-icon"></i>
      <div class="toast-content">${message}</div>
      <button class="toast-close" onclick="this.closest('.toast-custom').classList.add('toast-exit'); setTimeout(() => this.closest('.toast-custom').remove(), 400);">
        <i class="bi bi-x-lg"></i>
      </button>
    `;

    toastContainer.appendChild(toast);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      if (toast.parentNode) {
        toast.classList.add('toast-exit');
        setTimeout(() => {
          if (toast.parentNode) toast.remove();
        }, 400);
      }
    }, 5000);
  }

  // Make createToast globally accessible
  window.createToast = createToast;


  // ==========================================
  // 6. NAVBAR ACTIVE LINK
  // ==========================================
  const currentPath = window.location.pathname;
  const navLinks = document.querySelectorAll('#main-navbar .nav-link');

  navLinks.forEach(link => {
    const href = link.getAttribute('href');
    if (!href || href === '#') return;

    // Exact match for home
    if (href === '/' && currentPath === '/') {
      link.classList.add('active-link');
    }
    // Prefix match for other pages (but not home)
    else if (href !== '/' && currentPath.startsWith(href)) {
      link.classList.add('active-link');
    }
  });


  // ==========================================
  // 7. HERO PARALLAX EFFECT (subtle)
  // ==========================================
  const heroBg = document.querySelector('.hero-bg-image');

  if (heroBg) {
    window.addEventListener('scroll', () => {
      const scrolled = window.scrollY;
      if (scrolled < 800) {
        heroBg.style.transform = `scale(1.02) translateY(${scrolled * 0.15}px)`;
      }
    }, { passive: true });
  }


  // ==========================================
  // 8. SMOOTH HOVER TILT ON PRODUCT CARDS
  // ==========================================
  const productCards = document.querySelectorAll('.product-card');

  productCards.forEach(card => {
    card.addEventListener('mouseenter', function () {
      this.style.transition = 'transform 0.3s ease, box-shadow 0.3s ease';
    });

    card.addEventListener('mousemove', function (e) {
      const rect = this.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = (y - centerY) / 20;
      const rotateY = (centerX - x) / 20;

      this.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-4px)`;
    });

    card.addEventListener('mouseleave', function () {
      this.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0)';
    });
  });


  // ==========================================
  // 9. LAZY STAGGER ANIMATION
  // ==========================================
  // Automatically add stagger delays to children in a .stagger-children container
  const staggerContainers = document.querySelectorAll('.stagger-children');
  staggerContainers.forEach(container => {
    const children = container.querySelectorAll('.scroll-animate, .scroll-animate-scale');
    children.forEach((child, index) => {
      child.style.transitionDelay = `${index * 0.08}s`;
    });
  });


  // ==========================================
  // 10. NAVBAR SHRINK ON SCROLL
  // ==========================================
  const navbar = document.getElementById('main-navbar');

  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 80) {
        navbar.style.padding = '0.4rem 0';
        navbar.style.boxShadow = '0 2px 20px rgba(0,0,0,0.3)';
      } else {
        navbar.style.padding = '0.8rem 0';
        navbar.style.boxShadow = '';
      }
    }, { passive: true });
  }

});

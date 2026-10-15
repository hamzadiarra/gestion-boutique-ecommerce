/* Presentation only: never alter the source photograph or its URL. */
(() => {
  "use strict";
  document.querySelectorAll(".shop-product-media img").forEach(image => {
    const chooseFit = () => {
      const ratio = image.naturalWidth / image.naturalHeight;
      // Cover a square only when at least 75% of each original dimension survives.
      image.classList.toggle("is-balanced-photo", ratio >= 0.75 && ratio <= 4 / 3);
    };
    if (image.complete) chooseFit();
    else image.addEventListener("load", chooseFit, { once: true });
  });
})();

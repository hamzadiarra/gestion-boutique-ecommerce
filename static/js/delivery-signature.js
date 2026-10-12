(() => {
  "use strict";
  const form = document.getElementById("signature-form");
  if (!form) return;
  const canvas = document.getElementById("signature-canvas"), ctx = canvas.getContext("2d");
  const error = document.getElementById("signature-error");
  let pointer = null, drawn = false;
  function reset() {
    ctx.fillStyle = "white"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#111"; ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.lineJoin = "round";
    drawn = false; pointer = null; form.elements.signature.value = ""; error.textContent = "";
  }
  function point(e) {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX-r.left)*canvas.width/r.width, (e.clientY-r.top)*canvas.height/r.height];
  }
  canvas.addEventListener("pointerdown", e => {
    if (pointer !== null || (e.pointerType === "mouse" && e.button !== 0)) return;
    e.preventDefault(); pointer = e.pointerId; canvas.setPointerCapture(pointer);
    ctx.beginPath(); ctx.moveTo(...point(e));
  });
  canvas.addEventListener("pointermove", e => {
    if (e.pointerId !== pointer) return;
    e.preventDefault(); ctx.lineTo(...point(e)); ctx.stroke(); drawn = true;
  });
  function stop(e) { if (e.pointerId === pointer) pointer = null; }
  canvas.addEventListener("pointerup", stop); canvas.addEventListener("pointercancel", stop);
  document.getElementById("signature-clear").addEventListener("click", reset);
  form.addEventListener("submit", e => {
    if (!drawn) { e.preventDefault(); error.textContent = "Le destinataire doit signer avant de confirmer."; return; }
    form.elements.signature.value = canvas.toDataURL("image/png");
    form.querySelector('button:not([type="button"])').disabled = true;
  });
  reset();
})();

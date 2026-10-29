// The "Como funciona" guide: a dialog with one tab per part of the app.
// Opens from the floating ? (or any [data-open-guide]); opens by itself once per
// browser session until the member ticks "Não mostrar ao entrar".
(() => {
  const dialog = document.getElementById("guide");
  if (!dialog) return;

  const tabs = [...dialog.querySelectorAll("[data-tab]")];
  const panels = [...dialog.querySelectorAll("[data-panel]")];
  const prev = dialog.querySelector("[data-prev]");
  const next = dialog.querySelector("[data-next]");
  const hide = dialog.querySelector("[data-hide]");
  let i = 0;

  const show = (n) => {
    i = Math.max(0, Math.min(tabs.length - 1, n));
    tabs.forEach((t, k) => t.setAttribute("aria-selected", k === i ? "true" : "false"));
    panels.forEach((p, k) => (p.hidden = k !== i));
    tabs[i].scrollIntoView({ block: "nearest", inline: "nearest" });
    prev.disabled = i === 0;
    next.textContent = i === tabs.length - 1 ? "Fechar" : "Próximo";
  };

  const open = () => {
    show(0);
    dialog.showModal();
  };

  tabs.forEach((t, k) => t.addEventListener("click", () => show(k)));
  prev.addEventListener("click", () => show(i - 1));
  next.addEventListener("click", () => (i === tabs.length - 1 ? dialog.close() : show(i + 1)));
  dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
  // Click on the backdrop closes it.
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  document.querySelectorAll("[data-open-guide]").forEach((b) => b.addEventListener("click", open));

  hide.addEventListener("change", () => {
    fetch("/guia", { method: "POST", body: new URLSearchParams({ mostrar: hide.checked ? "0" : "1" }) });
  });

  if (dialog.hasAttribute("data-auto")) {
    let seen = false;
    try { seen = sessionStorage.getItem("guide-shown") === "1"; sessionStorage.setItem("guide-shown", "1"); } catch {}
    if (!seen) open();
  }
})();

// Episode board: drag cards between columns to change their status.
// Phones use the per-card "mover" select instead (HTML5 drag doesn't fire on touch).
(() => {
  const board = document.getElementById("board");
  if (!board) return;
  let dragged = null;

  const recount = () =>
    board.querySelectorAll(".column").forEach((col) => {
      const n = col.querySelectorAll(".ep-card").length;
      col.querySelector("[data-count]").textContent = n;
      const empty = col.querySelector(".empty-col");
      if (empty) empty.hidden = n > 0;
    });

  board.addEventListener("dragstart", (e) => {
    const card = e.target.closest(".ep-card");
    if (!card) return;
    dragged = card;
    card.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", card.dataset.id);
  });

  board.addEventListener("dragend", () => {
    if (dragged) dragged.classList.remove("dragging");
    board.querySelectorAll(".drop-target").forEach((c) => c.classList.remove("drop-target"));
    dragged = null;
  });

  board.addEventListener("dragover", (e) => {
    const col = e.target.closest(".column");
    if (!col || !dragged) return;
    e.preventDefault();
    board.querySelectorAll(".drop-target").forEach((c) => c !== col && c.classList.remove("drop-target"));
    col.classList.add("drop-target");
  });

  board.addEventListener("drop", async (e) => {
    const col = e.target.closest(".column");
    if (!col || !dragged) return;
    e.preventDefault();
    const card = dragged;
    const from = card.closest(".column");
    const status = col.dataset.status;
    col.classList.remove("drop-target");
    if (from === col) return;

    col.querySelector("[data-drop]").prepend(card);
    recount();
    card.classList.add("saving");
    try {
      const res = await fetch(`/episodios/${card.dataset.id}/status`, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: new URLSearchParams({ status }),
      });
      if (!res.ok) throw new Error(res.status);
      const select = card.querySelector(".move select");
      if (select) {
        [...select.options].forEach((o) => {
          o.selected = o.value === status;
          o.textContent = o.textContent.replace(/^→ /, "");
          if (o.value !== status) o.textContent = "→ " + o.textContent;
        });
      }
      // Some columns show different card details (votes, dates); refresh quietly.
      if (["publicado", "agendado"].includes(status) || ["ideia", "pauta"].includes(from.dataset.status)) {
        setTimeout(() => location.reload(), 400);
      }
    } catch {
      from.querySelector("[data-drop]").prepend(card);
      recount();
      alert("Não consegui mover o episódio. Confira a conexão e tente de novo.");
    } finally {
      card.classList.remove("saving");
    }
  });
})();

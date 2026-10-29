// Episode board: drag cards between columns to change their status.
// Pointer events, so it works with a mouse (press and move) and on touch
// screens (press and hold, then move). Taps still open links and vote.
(() => {
  const board = document.getElementById("board");
  if (!board) return;

  const HOLD_MS = 350; // touch: hold this long before the card lifts
  const MOVE_PX = 8; // mouse: move this far before the card lifts
  const EDGE_PX = 48; // auto-scroll when the pointer is this close to an edge

  let pending = null; // {card, x, y, pointerId, type, timer}
  let drag = null; // {card, ghost, from, dx, dy, x, y, over}
  let suppressClick = false;

  const columnAt = (x, y) => {
    const el = document.elementFromPoint(x, y);
    return el && el.closest ? el.closest(".column") : null;
  };

  const lift = () => {
    const { card, x, y } = pending;
    clearTimeout(pending.timer);
    pending = null;
    const rect = card.getBoundingClientRect();
    const ghost = card.cloneNode(true);
    ghost.classList.add("ghost");
    ghost.style.width = `${rect.width}px`;
    document.body.appendChild(ghost);
    card.classList.add("dragging");
    document.body.classList.add("is-dragging");
    drag = { card, ghost, from: card.closest(".column"), dx: x - rect.left, dy: y - rect.top, x, y, over: null };
    if (navigator.vibrate) navigator.vibrate(15);
    place();
    requestAnimationFrame(autoScroll);
  };

  const place = () => {
    const { ghost, x, y, dx, dy } = drag;
    ghost.style.transform = `translate(${x - dx}px, ${y - dy}px) rotate(2deg)`;
    const col = columnAt(x, y);
    if (col !== drag.over) {
      if (drag.over) drag.over.classList.remove("drop-target");
      if (col && col !== drag.from) col.classList.add("drop-target");
      drag.over = col;
    }
  };

  const autoScroll = () => {
    if (!drag) return;
    const { x, y } = drag;
    const r = board.getBoundingClientRect();
    if (x < r.left + EDGE_PX) board.scrollLeft -= 12;
    else if (x > r.right - EDGE_PX) board.scrollLeft += 12;
    // Each column scrolls on its own: scroll the one under the pointer.
    const list = drag.over && drag.over.querySelector("[data-drop]");
    if (list) {
      const l = list.getBoundingClientRect();
      if (y < l.top + EDGE_PX) list.scrollTop -= 12;
      else if (y > l.bottom - EDGE_PX) list.scrollTop += 12;
    }
    place();
    requestAnimationFrame(autoScroll);
  };

  const cancelPending = () => {
    if (pending) clearTimeout(pending.timer);
    pending = null;
  };

  board.addEventListener("pointerdown", (e) => {
    if (drag || e.button > 0) return;
    const card = e.target.closest(".ep-card");
    if (!card || e.target.closest("button, form, input, select")) return;
    pending = { card, x: e.clientX, y: e.clientY, type: e.pointerType };
    if (e.pointerType !== "mouse") pending.timer = setTimeout(lift, HOLD_MS);
  });

  window.addEventListener("pointermove", (e) => {
    if (pending) {
      const moved = Math.hypot(e.clientX - pending.x, e.clientY - pending.y);
      if (pending.type === "mouse" && moved > MOVE_PX) {
        e.preventDefault();
        lift();
      } else if (pending.type !== "mouse" && moved > MOVE_PX) {
        cancelPending(); // finger moved before the hold: it's a scroll
      }
    }
    if (drag) {
      e.preventDefault();
      drag.x = e.clientX;
      drag.y = e.clientY;
      place();
    }
  });

  // Once a card is lifted, stop the page from scrolling under the finger.
  window.addEventListener("touchmove", (e) => { if (drag) e.preventDefault(); }, { passive: false });

  const drop = async () => {
    const { card, ghost, from, over } = drag;
    drag = null;
    ghost.remove();
    card.classList.remove("dragging");
    document.body.classList.remove("is-dragging");
    board.querySelectorAll(".drop-target").forEach((c) => c.classList.remove("drop-target"));
    suppressClick = true;
    setTimeout(() => (suppressClick = false), 50);
    if (!over || over === from) return;

    const list = over.querySelector("[data-drop]");
    list.prepend(card);
    list.scrollTop = 0;
    card.classList.add("saving");
    try {
      const res = await fetch(`/episodios/${card.dataset.id}/status`, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: new URLSearchParams({ status: over.dataset.status }),
      });
      if (!res.ok) throw new Error(res.status);
      location.reload(); // re-sort by votes and refresh what the card shows in its new column
    } catch {
      from.querySelector("[data-drop]").prepend(card);
      card.classList.remove("saving");
      alert("Não consegui mover o episódio. Confira a conexão e tente de novo.");
    }
  };

  window.addEventListener("pointerup", () => {
    cancelPending();
    if (drag) drop();
  });
  window.addEventListener("pointercancel", () => {
    cancelPending();
    if (drag) drop();
  });

  // A drag ends with a click on whatever is under the pointer; ignore it.
  board.addEventListener("click", (e) => {
    if (suppressClick) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);
  // Links and images are natively draggable; that drag would cancel ours.
  board.addEventListener("dragstart", (e) => e.preventDefault());
  // Long-press on a link would open the browser's link menu instead of dragging.
  board.addEventListener("contextmenu", (e) => { if (e.target.closest(".ep-card")) e.preventDefault(); });
})();

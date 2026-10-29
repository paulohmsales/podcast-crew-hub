// Availability grid: paint your free slots (tap or drag), or inspect the group.
(() => {
  const grid = document.getElementById("grid");
  if (!grid) return;
  const total = Number(grid.dataset.total) || 1;
  const myName = grid.dataset.me;
  const whoAt = document.getElementById("who-at");
  const status = document.getElementById("save-status");
  const cells = [...grid.querySelectorAll("td[data-slot]")];

  // --- mode switch -----------------------------------------------------------
  const tabs = document.querySelectorAll(".mode-switch [data-mode]");
  const setMode = (mode) => {
    grid.dataset.mode = mode;
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.mode === mode)));
    document.querySelectorAll("[data-hint]").forEach((h) => (h.hidden = h.dataset.hint !== mode));
    whoAt.textContent = "";
    grid.querySelectorAll(".focus").forEach((c) => c.classList.remove("focus"));
  };
  tabs.forEach((t) => t.addEventListener("click", () => setMode(t.dataset.mode)));

  // --- group view ------------------------------------------------------------
  const describe = (cell) => {
    const when = cell.getAttribute("aria-label").split(": ")[0];
    const n = Number(cell.dataset.n);
    whoAt.textContent = n ? `${when} — ${n}/${total}: ${cell.dataset.who}` : `${when} — ninguém marcou`;
  };

  // --- painting --------------------------------------------------------------
  let painting = null; // true = adding, false = removing
  let dirty = false;

  const applyMine = (cell, on) => {
    if (cell.classList.contains("mine") === on) return;
    cell.classList.toggle("mine", on);
    const names = cell.dataset.who ? cell.dataset.who.split(", ") : [];
    const next = on ? [...names, myName].sort((a, b) => a.localeCompare(b)) : names.filter((n) => n !== myName);
    cell.dataset.who = next.join(", ");
    cell.dataset.n = next.length;
    cell.style.setProperty("--heat", next.length / total);
    dirty = true;
  };

  const cellAt = (e) => {
    const el = document.elementFromPoint(e.clientX, e.clientY);
    return el && el.matches && el.matches("td[data-slot]") && grid.contains(el) ? el : null;
  };

  grid.addEventListener("pointerdown", (e) => {
    const cell = cellAt(e);
    if (!cell) return;
    if (grid.dataset.mode === "group") {
      grid.querySelectorAll(".focus").forEach((c) => c.classList.remove("focus"));
      cell.classList.add("focus");
      describe(cell);
      return;
    }
    e.preventDefault();
    painting = !cell.classList.contains("mine");
    applyMine(cell, painting);
  });

  grid.addEventListener("pointermove", (e) => {
    if (painting === null) return;
    const cell = cellAt(e);
    if (cell) applyMine(cell, painting);
  });

  const endPaint = () => {
    if (painting === null) return;
    painting = null;
    if (dirty) save();
  };
  window.addEventListener("pointerup", endPaint);
  window.addEventListener("pointercancel", endPaint);

  // --- who answered ----------------------------------------------------------
  const LABELS = { can: "pode", cant: "não pode", todo: "falta" };
  const markMe = (state) => {
    const chip = [...document.querySelectorAll("#who [data-member]")].find((c) => c.dataset.member === myName);
    if (!chip) return;
    chip.className = `chip ${state}`;
    chip.querySelector(".chip-state").textContent = LABELS[state];
    const chips = document.querySelectorAll("#who [data-member]");
    const answered = [...chips].filter((c) => !c.classList.contains("todo")).length;
    document.getElementById("who-count").textContent = `${answered}/${chips.length}`;
  };

  // --- saving ----------------------------------------------------------------
  let inflight = null;
  let again = false;

  async function save() {
    dirty = false;
    if (inflight) {
      again = true;
      return;
    }
    const slots = cells.filter((c) => c.classList.contains("mine")).map((c) => c.dataset.slot);
    status.textContent = "Salvando…";
    try {
      inflight = fetch(grid.dataset.saveUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slots }),
      });
      const res = await inflight;
      if (!res.ok) throw new Error(await res.text());
      status.textContent = slots.length
        ? `Salvo ✓ — ${slots.length} horário${slots.length > 1 ? "s" : ""} marcado${slots.length > 1 ? "s" : ""}.`
        : "Salvo ✓ — você marcou que não pode em nenhum.";
      markMe(slots.length ? "can" : "cant");
    } catch (err) {
      status.textContent = "Não consegui salvar. Confira a conexão e toque de novo.";
      dirty = true;
    } finally {
      inflight = null;
      if (again) {
        again = false;
        save();
      }
    }
  }

  const noneBtn = document.getElementById("none-btn");
  if (noneBtn) {
    noneBtn.addEventListener("click", () => {
      if (cells.some((c) => c.classList.contains("mine")) && !confirm("Limpar todos os seus horários?")) return;
      cells.forEach((c) => applyMine(c, false));
      save();
    });
  }
})();

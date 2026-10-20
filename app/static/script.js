// Shared episode script: autosaves while typing and pulls others' edits.
// The server merges concurrent edits (diff-match-patch), so we always send
// what we started from (base) along with what we have now.
(() => {
  const area = document.getElementById("script");
  if (!area) return;
  const url = area.dataset.url;
  const status = document.getElementById("script-status");
  const presence = document.getElementById("script-presence");

  let base = area.value; // text as last agreed with the server
  let version = Number(area.dataset.version);
  let dirty = false;
  let inflight = false;
  let timer = null;

  const autosize = () => {
    area.style.height = "auto";
    area.style.height = `${Math.max(area.scrollHeight + 2, window.innerHeight * 0.55)}px`;
  };

  // Where the cursor should land after the text changes from `old` to `nu`.
  const mapPos = (old, nu, pos) => {
    let p = 0;
    while (p < old.length && p < nu.length && old[p] === nu[p]) p++;
    if (pos <= p) return pos;
    let s = 0;
    while (s < old.length - p && s < nu.length - p && old[old.length - 1 - s] === nu[nu.length - 1 - s]) s++;
    if (pos >= old.length - s) return pos + (nu.length - old.length);
    return Math.min(pos, nu.length);
  };

  const replaceText = (text) => {
    if (text === area.value) return;
    const old = area.value;
    const focused = document.activeElement === area;
    const [a, b] = [area.selectionStart, area.selectionEnd];
    area.value = text;
    if (focused) area.setSelectionRange(mapPos(old, text, a), mapPos(old, text, b));
    autosize();
  };

  const showPresence = (names) => {
    presence.textContent = names && names.length ? `✎ ${names.join(", ")} ${names.length > 1 ? "estão" : "está"} editando agora` : "";
  };

  async function save() {
    clearTimeout(timer);
    if (inflight) {
      timer = setTimeout(save, 300);
      return;
    }
    const sent = area.value;
    if (sent === base) {
      dirty = false;
      return;
    }
    inflight = true;
    dirty = false;
    let retryIn = 800;
    status.textContent = "Salvando…";
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ base_version: version, base_text: base, text: sent }),
      });
      const data = await res.json();
      if (res.status === 409) {
        // Couldn't merge: keep the newer server text unless we kept typing.
        if (area.value === sent) replaceText(data.text);
        base = data.text;
        version = data.version;
        status.textContent = "Alguém mudou o mesmo trecho; o texto foi atualizado. Confira sua última edição.";
      } else if (!res.ok) {
        throw new Error(res.status);
      } else {
        if (area.value === sent) {
          replaceText(data.text); // may include others' merged changes
          base = data.text;
          version = data.version;
        } else {
          // Kept typing meanwhile: next save merges from what we sent.
          base = sent;
          version = -1;
          dirty = true;
        }
        status.textContent = `Salvo às ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
        showPresence(data.editing);
      }
    } catch {
      dirty = true;
      retryIn = 4000;
      status.textContent = "Sem conexão. Tentando salvar de novo…";
    } finally {
      inflight = false;
      if (dirty) {
        clearTimeout(timer);
        timer = setTimeout(save, retryIn);
      }
    }
  }

  async function poll() {
    if (document.hidden) return;
    try {
      const res = await fetch(`${url}.json`, { headers: { Accept: "application/json" } });
      if (!res.ok) return;
      const data = await res.json();
      showPresence(data.editing);
      if (data.version > version && !dirty && !inflight && area.value === base) {
        replaceText(data.text);
        base = data.text;
        version = data.version;
        if (data.updated_by) status.textContent = `Atualizado: ${data.updated_by}, ${data.updated_at}`;
      }
    } catch {
      /* offline: try again next tick */
    }
  }

  area.addEventListener("input", () => {
    dirty = true;
    autosize();
    clearTimeout(timer);
    timer = setTimeout(save, 800);
  });
  area.addEventListener("blur", () => dirty && save());
  window.addEventListener("beforeunload", (e) => {
    if (dirty || inflight) e.preventDefault();
  });
  document.addEventListener("visibilitychange", () => !document.hidden && poll());

  autosize();
  poll();
  setInterval(poll, 3000);
})();

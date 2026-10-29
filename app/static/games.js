// Episode Jogos tab: search Ludopedia as you type and add or remove games
// without reloading, so the search box keeps focus for the next game.
(() => {
  const form = document.querySelector(".game-search");
  if (!form) return;
  const input = form.querySelector('input[name="jogo"]');
  const results = document.getElementById("game-results");
  const list = document.getElementById("episode-games");
  const count = document.getElementById("game-count");
  const tabCount = document.querySelector('.ep-tabs a[href$="aba=jogos"]');
  const headers = { "X-Requested-With": "fetch" };
  let timer = null;
  let seq = 0;

  const search = async () => {
    const q = input.value.trim();
    const mine = ++seq;
    history.replaceState(null, "", `?aba=jogos${q ? `&jogo=${encodeURIComponent(q)}` : ""}`);
    if (q.length < 2) {
      results.innerHTML = "";
      return;
    }
    results.classList.add("loading");
    try {
      const res = await fetch(`${form.dataset.url}?jogo=${encodeURIComponent(q)}`, { headers });
      const html = await res.text();
      if (mine === seq) results.innerHTML = html;
    } catch {
      if (mine === seq) results.innerHTML = '<p class="error small" role="alert">Não consegui buscar. Tente de novo.</p>';
    } finally {
      if (mine === seq) results.classList.remove("loading");
    }
  };

  const setCount = (n) => {
    count.textContent = n;
    let badge = tabCount?.querySelector("span");
    if (tabCount && !badge && n > 0) {
      tabCount.append(" ", (badge = document.createElement("span")));
    }
    if (badge) n > 0 ? (badge.textContent = n) : badge.remove();
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(search, 250);
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    clearTimeout(timer);
    search();
  });

  document.addEventListener("submit", async (e) => {
    const f = e.target;
    const adding = f.matches(".game-add");
    if (!adding && !f.matches(".game-remove")) return;
    e.preventDefault();
    const btn = f.querySelector("button");
    btn.disabled = true;
    if (adding) btn.textContent = "Adicionando…";
    try {
      const res = await fetch(f.action, { method: "POST", body: new FormData(f), headers });
      if (!res.ok) throw new Error(await res.text());
      list.innerHTML = await res.text();
      setCount(Number(res.headers.get("X-Games-Count")));
      if (adding) {
        const done = document.createElement("span");
        done.className = "muted small";
        done.textContent = "adicionado";
        f.replaceWith(done);
        input.focus();
        input.select(); // typing the next name replaces this one
      } else if (input.value.trim()) {
        search(); // the removed game gets its Adicionar button back
      }
    } catch (err) {
      btn.disabled = false;
      if (adding) btn.textContent = "Adicionar";
      alert(err.message || "Não deu certo. Tente de novo.");
    }
  });

  if (matchMedia("(pointer: fine)").matches) input.focus();
})();

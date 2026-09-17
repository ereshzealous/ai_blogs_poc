// Web channel: polls the capability state, renders the server-made card, turns available_actions into buttons.
// It never decides what may happen next; the response's available_actions do.
const $ = (id) => document.getElementById(id);
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } } };
let current = new URLSearchParams(location.search).get("wf") || "";
let timer = null;

const subject = () => $("subject").value;
const headers = () => ({ "X-OIDC-Subject": subject(), "Content-Type": "application/json" });
const toast = (msg, bad = false) => { $("toast").textContent = msg; $("toast").className = "toast" + (bad ? " bad" : ""); };

async function whoami() {
  const r = await fetch("/web/api/me", { headers: headers() });
  const me = r.ok ? await r.json() : null;
  $("identity").textContent = me ? `${subject()} → principal ${me.principal_id} · roles: ${me.roles.join(", ")}` : "identity not linked";
}

async function load() {
  if (!current) return;
  const r = await fetch(`/web/api/workflows/${encodeURIComponent(current)}`, { headers: headers() });
  if (!r.ok) { toast((await r.json()).detail?.message || `error ${r.status}`, true); return; }
  const page = await r.json();
  $("view").innerHTML = page.card;
  for (const b of $("view").querySelectorAll("button.act")) b.addEventListener("click", () => act(b));
  const terminal = ["COMPLETED", "REJECTED"].includes(page.response.status);
  clearTimeout(timer);
  if (!terminal) timer = setTimeout(load, 1500);
}

async function act(button) {
  button.disabled = true;
  const r = await fetch(`/web/api/workflows/${encodeURIComponent(current)}/actions`, {
    method: "POST", headers: headers(),
    body: JSON.stringify({ action_id: button.dataset.action, binding: button.dataset.binding || null }) });
  const body = await r.json();
  if (!r.ok) { toast(body.detail?.message || `error ${r.status}`, true); button.disabled = false; return; }
  toast(`${button.textContent} accepted as ${body.response.actor.principal_id} via web`);
  $("view").innerHTML = body.card;
  clearTimeout(timer); timer = setTimeout(load, 800);
}

$("open").addEventListener("submit", (e) => {
  e.preventDefault(); current = $("wf").value.trim(); toast("");
  history.replaceState(null, "", `?wf=${encodeURIComponent(current)}`); load();
});
$("subject").addEventListener("change", () => { store.set("subject", subject()); toast(""); whoami(); load(); });

const saved = store.get("subject");
if (saved && [...$("subject").options].some((o) => o.value === saved)) $("subject").value = saved;
const asParam = new URLSearchParams(location.search).get("as");
if (asParam) $("subject").value = asParam;
$("wf").value = current;
whoami(); load();

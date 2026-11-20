// Saarthi live page: shows the character exactly as it is on the owner's desktop, and lets the visitor
// poke / tickle / slap / kick a football / throw a pillow / send love. No menus, no access to anything else.
"use strict";

const FALLBACK = {
  typing_fast: "typing_slow", typing_slow: "idle", scrolling: "idle", watching: "idle", afk: "idle",
  sleeping: "afk", waking: "happy", stretch: "happy", alert: "happy", happy: "idle", poked: "happy",
  giggle: "happy", break: "idle", breathe: "stretch", walk: "idle", eat: "break", think: "typing_slow",
};
// what a visitor's action looks like (state, take, seconds)
const REACTION = {
  poke: ["poked", "", 1.6], tickle: ["giggle", "", 2.0], slap: ["poked", "slap", 1.6],
  ball: ["poked", "ball", 1.8], pillow: ["poked", "pillow", 1.8], love: ["poked", "love", 3.0],
  kiss: ["poked", "kiss", 3.2], hug: ["poked", "hug", 3.2], angry: ["poked", "angry", 3.2], boots: ["poked", "boots", 1.6], jeans: ["poked", "jeans", 1.6],
};
const DOING = {
  typing: "is typing away ⌨️", scrolling: "is reading 📜", video: "is watching a video 🎬",
  tutorial: "is learning from a tutorial 📚", music: "is listening to music 🎧", break: "is on a chai break ☕",
  lunch: "is having lunch 🍱", breathing: "is doing a breathing exercise 🧘", away: "stepped away 🚶",
  sleeping: "is away, the laptop is resting 😴", walking: "is taking a little walk 🚶", idle: "is at the laptop 💻",
};

const room = location.pathname.split("/").filter(Boolean)[1] || new URLSearchParams(location.search).get("room");
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const $doing = document.getElementById("doing");
const $status = document.getElementById("status");
const $statusText = document.getElementById("statusText");
const $bubble = document.getElementById("bubble");

let manifest = {};
const images = new Map(); // path -> Image
let shown = { state: "idle", take: "", mirror: false, since: performance.now() };
let remote = null; // latest {type:"state"} from the owner
let local = null; // a reaction playing on this page: {state, take, until, since}
let ownerOnline = false;
let bubbleTimer = 0;

function img(path) {
  let im = images.get(path);
  if (!im) { im = new Image(); im.src = `/skin/${path}`; images.set(path, im); }
  return im;
}
function anim(state, take) {
  if (take && manifest[`${state}.${take}`]) return manifest[`${state}.${take}`];
  let s = state, seen = new Set();
  while (!manifest[s] && FALLBACK[s] && !seen.has(s)) { seen.add(s); s = FALLBACK[s]; }
  return manifest[s] || manifest.idle;
}
function preload(a) { if (a) a.frames.forEach(img); }

function setShown(state, take, mirror) {
  if (state !== shown.state || take !== shown.take) shown = { state, take, mirror, since: performance.now() };
  shown.mirror = mirror;
  preload(anim(state, take));
}

function draw(now) {
  requestAnimationFrame(draw);
  if (local && now > local.until) local = null;
  if (local) setShown(local.state, local.take, false);
  else if (remote) setShown(remote.walking ? "walk" : remote.state, remote.walking ? "" : remote.take || "", !!remote.mirror);
  const a = anim(shown.state, shown.take);
  if (!a) return;
  const t = (now - shown.since) / 1000;
  let i = Math.floor(t * a.fps);
  i = a.loop ? i % a.frames.length : Math.min(i, a.frames.length - 1);
  const im = img(a.frames[i]);
  if (!im.complete || !im.naturalWidth) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  if (shown.mirror) { ctx.translate(canvas.width, 0); ctx.scale(-1, 1); }
  ctx.drawImage(im, 0, 0, canvas.width, canvas.height);
  ctx.restore();
}

function say(text, ms = 5000) {
  $bubble.textContent = text;
  $bubble.classList.add("show");
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => $bubble.classList.remove("show"), ms);
}

function ago(ms) {
  const m = Math.round(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}
function renderStatus() {
  const name = (remote && remote.name) || "Saarthi";
  document.title = `${name} · live`;
  document.querySelectorAll(".who").forEach((el) => { el.textContent = name; });
  if (ownerOnline && remote) {
    $doing.textContent = `${name} ${DOING[remote.kind] || DOING.idle}`;
    $status.classList.remove("off");
    $statusText.textContent = "live";
  } else {
    $doing.textContent = remote ? `${name} is offline` : "Waiting for Saarthi…";
    $status.classList.add("off");
    $statusText.textContent = remote && remote.at ? `last seen ${ago(Date.now() - remote.at)}` : "offline";
  }
}

function react(action) {
  const r = REACTION[action];
  if (!r) return;
  local = { state: r[0], take: r[1], until: performance.now() + r[2] * 1000 };
  setShown(r[0], r[1], false);
}

let ws = null;
let retry = 1000;
function connect() {
  if (!room) { $doing.textContent = "This link is missing its room."; return; }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${encodeURIComponent(room)}?role=viewer`);
  ws.onopen = () => { retry = 1000; };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === "state") { remote = m; renderStatus(); applySwitches(); }
    else if (m.type === "owner") { ownerOnline = m.online; renderStatus(); }
    else if (m.type === "say") say(m.text);
    else if (m.type === "history") { $msgs.innerHTML = ""; m.messages.forEach(addMsg); if (!m.messages.length) { $msgs.innerHTML = `<div class="empty">Say hi to ${((remote && remote.name) || "him")} 👋</div>`; } }
    else if (m.type === "chat") { addMsg(m); if (m.from === "owner") say(`💬 ${m.text}`, 7000); }
    else if (m.type === "action" && performance.now() - sentAt > 1500) react(m.action); // not our own echo
  };
  ws.onclose = () => { ownerOnline = false; renderStatus(); setTimeout(connect, retry); retry = Math.min(retry * 2, 30000); };
}

const $msgs = document.getElementById("msgs");
const $chat = document.getElementById("chat");
const $input = document.getElementById("chatInput");
function addMsg(m) {
  const empty = $msgs.querySelector(".empty");
  if (empty) empty.remove();
  const d = document.createElement("div");
  d.className = `msg ${m.from === "viewer" ? "me" : "him"}`;
  d.textContent = m.text;
  const t = document.createElement("small");
  t.textContent = new Date(m.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  d.appendChild(t);
  $msgs.appendChild(d);
  $msgs.scrollTop = $msgs.scrollHeight;
}
document.getElementById("chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $input.value.trim();
  if (!text || !ws || ws.readyState !== 1) return;
  ws.send(JSON.stringify({ type: "chat", text }));
  $input.value = "";
});
// quick emojis (phones also have their own emoji keyboard)
const EMOJIS = ["😀", "😂", "😍", "🥰", "😘", "😜", "🤗", "🥺", "😢", "😡", "😤", "🙄", "👍", "🙏", "❤️", "💕", "💋", "🔥", "🎉", "😴"];
const $emojis = document.getElementById("emojis");
for (const e of EMOJIS) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = e;
  b.addEventListener("click", () => {
    const at = $input.selectionStart ?? $input.value.length;
    $input.value = $input.value.slice(0, at) + e + $input.value.slice($input.selectionEnd ?? at);
    $input.focus();
    $input.selectionStart = $input.selectionEnd = at + e.length;
  });
  $emojis.appendChild(b);
}
document.getElementById("emojiBtn").addEventListener("click", () => {
  $emojis.classList.toggle("open");
  $input.focus();
});

// the owner's switches: hide what he turned off
function applySwitches() {
  const actions = !remote || remote.actions !== false;
  const chat = !remote || remote.chat !== false;
  document.getElementById("actions").classList.toggle("hidden", !actions);
  document.getElementById("hint").classList.toggle("hidden", !actions);
  $chat.classList.toggle("hidden", !chat);
}

let sentAt = 0;
function send(action) {
  sentAt = performance.now();
  react(action); // feel it at once; the echo from the room is ignored while it plays
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "action", action }));
}

document.querySelectorAll("#actions button").forEach((b) => b.addEventListener("click", () => send(b.dataset.a)));
// Which part of him was tapped: like the desktop app, by where it is on his body and by colour
// (dark blue = jeans, brown = shoes). Taps on empty space do nothing.
function partAt(x, y) {
  const w = canvas.width, h = canvas.height;
  const data = ctx.getImageData(0, 0, w, h).data;
  let top = h, bottom = 0;
  for (let yy = 0; yy < h; yy += 2) {
    for (let xx = 0; xx < w; xx += 2) {
      if (data[(yy * w + xx) * 4 + 3] > 24) { if (yy < top) top = yy; if (yy > bottom) bottom = yy; break; }
    }
  }
  if (bottom <= top) return null;
  let hit = false, jeans = 0, boots = 0;
  const down = (y - top) / (bottom - top);
  for (let dy = -6; dy <= 6; dy += 2) {
    for (let dx = -6; dx <= 6; dx += 2) {
      const xx = Math.round(x + dx), yy = Math.round(y + dy);
      if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
      const i = (yy * w + xx) * 4, a = data[i + 3];
      if (a > 24) hit = true;
      if (a < 120 || down <= 0.62) continue;
      const r = data[i], g = data[i + 1], b = data[i + 2], bright = (r + g + b) / 3;
      if (b > r + 12 && bright < 95) jeans++;
      else if (r > b + 25 && bright < 110 && r < 150 && down > 0.78) boots++;
    }
  }
  if (!hit) return null;
  if (Math.max(jeans, boots) >= 6) return boots > jeans ? "boots" : "jeans";
  return down < 0.4 ? "poke" : "tickle";
}
canvas.addEventListener("click", (e) => {
  const r = canvas.getBoundingClientRect();
  if (remote && remote.actions === false) return;
  const part = partAt((e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height);
  if (part) send(part);
});
canvas.addEventListener("contextmenu", (e) => e.preventDefault());
canvas.addEventListener("dblclick", (e) => e.preventDefault());
setInterval(renderStatus, 30000);

fetch("/skin/manifest.json").then((r) => r.json()).then((m) => {
  manifest = m;
  preload(manifest.idle);
  Object.values(REACTION).forEach(([s, t]) => preload(anim(s, t)));
  requestAnimationFrame(draw);
  connect();
});

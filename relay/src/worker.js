// Saarthi live relay (Cloudflare Worker + one Durable Object per shared room).
//
//   Saarthi (owner)  --ws /ws/<room>?role=owner&token=..-->  Room  <--ws /ws/<room>?role=viewer--  browsers
//
// The owner sends what the character is doing ({type:"state"} and {type:"say"}); the room keeps the
// latest and fans it out to every viewer. A viewer can only send whitelisted fun actions (poke, football,
// ...) which go back to the owner. The first owner to connect claims the room with its token; after that
// only that token can drive it. The page itself is a static asset: /v/<room>.

const ACTIONS = new Set(["poke", "tickle", "slap", "ball", "pillow", "love", "kiss", "hug", "angry", "boots", "jeans"]);
const ROOM_RE = /^[A-Za-z0-9_-]{16,64}$/;
const MAX_MSG = 4096;
const ACTION_GAP_MS = 800; // per viewer
const CHAT_GAP_MS = 700;
const CHAT_MAX = 500; // characters per message
const CHAT_KEEP = 50; // messages kept for a page that opens later

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] === "v" && parts.length === 2) {
      // the viewer page: same HTML for every room; the room id is read from the URL
      return env.ASSETS.fetch(new Request(new URL("/", url), request));
    }
    if (parts[0] === "ws" && parts.length === 2) {
      if (!ROOM_RE.test(parts[1])) return new Response("bad room", { status: 400 });
      if (request.headers.get("Upgrade") !== "websocket") return new Response("websocket only", { status: 426 });
      const stub = env.ROOMS.get(env.ROOMS.idFromName(parts[1]));
      return stub.fetch(request);
    }
    if (url.pathname === "/") return new Response("Saarthi live relay", { status: 200 });
    return env.ASSETS.fetch(request);
  },
};

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export class Room {
  constructor(state) {
    this.state = state;
    this.owner = null;
    this.viewers = new Set();
    this.last = null; // latest {type:"state"} from the owner
    this.lastSay = null;
    this.chat = [];
    this.ready = state.blockConcurrencyWhile(async () => {
      this.tokenHash = (await state.storage.get("tokenHash")) || null;
      this.last = (await state.storage.get("last")) || null;
      this.chat = (await state.storage.get("chat")) || [];
    });
  }

  async fetch(request) {
    await this.ready;
    const url = new URL(request.url);
    const role = url.searchParams.get("role");
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();
    if (role === "owner") {
      const token = url.searchParams.get("token") || "";
      if (token.length < 20) return new Response("token too short", { status: 403 });
      const hash = await sha256(token);
      if (!this.tokenHash) {
        this.tokenHash = hash; // first owner claims the room
        await this.state.storage.put("tokenHash", hash);
      } else if (hash !== this.tokenHash) {
        return new Response("not your room", { status: 403 });
      }
      this.attachOwner(server);
    } else {
      this.attachViewer(server);
    }
    return new Response(null, { status: 101, webSocket: client });
  }

  // the owner's switches, sent with every state: {actions: bool, chat: bool}
  allows(what) {
    return !this.last || this.last[what] !== false;
  }

  async addChat(from, text) {
    const m = { type: "chat", from, text: String(text).slice(0, CHAT_MAX), at: Date.now() };
    this.chat.push(m);
    if (this.chat.length > CHAT_KEEP) this.chat.splice(0, this.chat.length - CHAT_KEEP);
    await this.state.storage.put("chat", this.chat);
    this.broadcast(m);
    if (this.owner) { try { this.owner.send(JSON.stringify(m)); } catch (e) {} }
  }

  attachOwner(ws) {
    if (this.owner) {
      try { this.owner.close(1000, "replaced"); } catch (e) {}
    }
    this.owner = ws;
    this.broadcast({ type: "owner", online: true });
    this.tellViewers();
    try { ws.send(JSON.stringify({ type: "history", messages: this.chat })); } catch (e) {}
    ws.addEventListener("message", async (ev) => {
      if (typeof ev.data !== "string" || ev.data.length > MAX_MSG) return;
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg.type === "state") {
        this.last = { ...msg, at: Date.now() };
        this.broadcast(this.last);
        await this.state.storage.put("last", this.last);
      } else if (msg.type === "say" && typeof msg.text === "string") {
        this.lastSay = { type: "say", text: msg.text.slice(0, 300), at: Date.now() };
        this.broadcast(this.lastSay);
      } else if (msg.type === "chat" && typeof msg.text === "string" && msg.text.trim()) {
        await this.addChat("owner", msg.text.trim());
      }
    });
    const gone = () => {
      if (this.owner === ws) {
        this.owner = null;
        this.broadcast({ type: "owner", online: false });
      }
    };
    ws.addEventListener("close", gone);
    ws.addEventListener("error", gone);
  }

  // how many pages are open right now, for the green dot on the owner's Saarthi
  tellViewers() {
    if (this.owner) { try { this.owner.send(JSON.stringify({ type: "viewers", count: this.viewers.size })); } catch (e) {} }
  }

  attachViewer(ws) {
    this.viewers.add(ws);
    this.tellViewers();
    let lastAction = 0;
    let lastChat = 0;
    const send = (m) => { try { ws.send(JSON.stringify(m)); } catch (e) {} };
    send({ type: "owner", online: !!this.owner });
    if (this.last) send(this.last);
    if (this.allows("chat")) send({ type: "history", messages: this.chat });
    ws.addEventListener("message", async (ev) => {
      if (typeof ev.data !== "string" || ev.data.length > 2048) return;
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      const now = Date.now();
      if (msg.type === "chat" && typeof msg.text === "string" && msg.text.trim() && this.allows("chat")) {
        if (now - lastChat < CHAT_GAP_MS) return;
        lastChat = now;
        await this.addChat("viewer", msg.text.trim());
        return;
      }
      if (msg.type !== "action" || !ACTIONS.has(msg.action) || !this.allows("actions")) return;
      if (now - lastAction < ACTION_GAP_MS) return;
      lastAction = now;
      const out = { type: "action", action: msg.action, at: now };
      this.broadcast(out); // every open page plays it
      if (this.owner) { try { this.owner.send(JSON.stringify(out)); } catch (e) {} }
    });
    const gone = () => { if (this.viewers.delete(ws)) this.tellViewers(); };
    ws.addEventListener("close", gone);
    ws.addEventListener("error", gone);
  }

  broadcast(msg) {
    const text = JSON.stringify(msg);
    for (const ws of this.viewers) {
      try { ws.send(text); } catch (e) { if (this.viewers.delete(ws)) this.tellViewers(); }
    }
  }
}

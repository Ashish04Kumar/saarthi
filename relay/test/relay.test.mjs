// End-to-end check against `wrangler dev` (http://127.0.0.1:8787):  node --experimental-websocket test/relay.test.mjs
import assert from "node:assert/strict";

const BASE = process.env.RELAY || "ws://127.0.0.1:8787";
const room = "test" + Math.random().toString(36).slice(2) + "abcdefghijkl";
const TOKEN = "t".repeat(32);

function open(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    const inbox = [];
    ws.onmessage = (e) => inbox.push(JSON.parse(e.data));
    ws.onopen = () => res({ ws, inbox });
    ws.onerror = () => rej(new Error("connect failed: " + url));
  });
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 3000) {
  const t = Date.now();
  while (Date.now() - t < ms) { if (fn()) return; await wait(50); }
  throw new Error("timed out");
}

const owner = await open(`${BASE}/ws/${room}?role=owner&token=${TOKEN}`);
owner.ws.send(JSON.stringify({ type: "state", state: "watching", take: "popcorn", kind: "video", name: "Ashish" }));
await wait(200);

const viewer = await open(`${BASE}/ws/${room}?role=viewer`);
await until(() => viewer.inbox.some((m) => m.type === "state"));
assert.equal(viewer.inbox.find((m) => m.type === "owner").online, true);
assert.equal(viewer.inbox.find((m) => m.type === "state").kind, "video");

await until(() => owner.inbox.some((m) => m.type === "viewers" && m.count === 1)); // green dot on
viewer.ws.send(JSON.stringify({ type: "action", action: "ball" }));
await until(() => owner.inbox.some((m) => m.type === "action"));
assert.equal(owner.inbox.find((m) => m.type === "action").action, "ball");

viewer.ws.send(JSON.stringify({ type: "action", action: "ball" })); // too soon: dropped
viewer.ws.send(JSON.stringify({ type: "action", action: "rm -rf" })); // not allowed
await wait(300);
assert.equal(owner.inbox.filter((m) => m.type === "action").length, 1);

// chat both ways, and a page that opens later gets the history
viewer.ws.send(JSON.stringify({ type: "chat", text: "Kya kar rahe ho? 😄" }));
await until(() => owner.inbox.some((m) => m.type === "chat" && m.from === "viewer"));
owner.ws.send(JSON.stringify({ type: "chat", text: "Code likh raha hoon" }));
await until(() => viewer.inbox.some((m) => m.type === "chat" && m.from === "owner"));
const late = await open(`${BASE}/ws/${room}?role=viewer`);
await until(() => late.inbox.some((m) => m.type === "history"));
assert.deepEqual(late.inbox.find((m) => m.type === "history").messages.map((m) => m.from), ["viewer", "owner"]);
await until(() => owner.inbox.filter((m) => m.type === "viewers").pop().count === 2);
late.ws.close();
await until(() => owner.inbox.filter((m) => m.type === "viewers").pop().count === 1);

// switches: with actions and chat off, the page can't send either
owner.ws.send(JSON.stringify({ type: "state", state: "idle", kind: "idle", name: "Ashish", actions: false, chat: false }));
await wait(200);
const before = owner.inbox.length;
await wait(900);
viewer.ws.send(JSON.stringify({ type: "action", action: "poke" }));
viewer.ws.send(JSON.stringify({ type: "chat", text: "hello?" }));
await wait(400);
assert.equal(owner.inbox.filter((m, i) => i >= before && (m.type === "action" || m.type === "chat")).length, 0);
owner.ws.send(JSON.stringify({ type: "state", state: "idle", kind: "idle", name: "Ashish", actions: true, chat: true }));

owner.ws.send(JSON.stringify({ type: "say", text: "Good one! 😄" }));
await until(() => viewer.inbox.some((m) => m.type === "say"));

let refused = false;
try { await open(`${BASE}/ws/${room}?role=owner&token=${"x".repeat(32)}`); } catch { refused = true; }
assert.ok(refused, "someone else's token must not take over the room");

owner.ws.close();
await until(() => viewer.inbox.some((m) => m.type === "owner" && m.online === false));
viewer.ws.close();
console.log("relay ok");
process.exit(0);

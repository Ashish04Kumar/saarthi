# Saarthi live link (relay)

A tiny Cloudflare Worker that lets someone watch your Saarthi live in a browser (phone or laptop) and play
with it: poke, tickle, slap, football, pillow, love. Your Saarthi connects to it; their page connects to it.

- They see: the same animation as your desktop, a general "what he's doing" (typing, a video, a tutorial,
  music, a break, lunch, breathing, away…) and the shareable bubble lines. Never titles, reminders, notes,
  calendar, the morning brief, weather or traffic.
- They can't open menus or anything else; only the six actions.
- The room id in the link is random; only your laptop's secret token can drive it.

## Deploy (free plan is enough)

```bash
cd relay
npm install
npx wrangler login          # opens the browser: sign in to your Cloudflare account
npm run deploy              # copies the skin and deploys; prints https://saarthi-live.<you>.workers.dev
npm test                    # (optional, against `npm run dev` on 127.0.0.1:8787)
```

Then in `~/.config/saarthi/config.json` set `"share_url": "https://saarthi-live.<you>.workers.dev"`,
`"share_name"` (your name on the page) and `"share_friend"` (who you share it with), restart Saarthi and use
the menu **🔗 Live link → Share live** and **Copy link**. **Show their actions here** decides whether their
pokes and footballs also play on your desktop.

Redeploy (`npm run deploy`) after the character's animations change, so the page has the new frames.

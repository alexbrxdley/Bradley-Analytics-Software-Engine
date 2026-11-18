# Bradley Analytics notification server

Live game alerts (tip-off, final score, close game in the 4th, big performances, filtered by team and player) already
work on the site **while it's open in a tab**: `docs/assets/notify.js` follows the night's games itself. This server is
what sends them **when the site is closed**, to phones (the Home Screen app on iPhone/iPad, any browser on Android) and
computers. It's a small Cloudflare Worker; the free plan is enough.

## One-time setup (about 10 minutes)

1. **Cloudflare account.** Sign up at cloudflare.com (free), then on your computer, in this `worker/` folder:

   ```
   npm install -g wrangler        # or use `npx wrangler` for each command below
   wrangler login
   ```

2. **Storage.** Create the KV namespace and paste the `id` it prints into `wrangler.toml` (replacing
   `PASTE_THE_KV_NAMESPACE_ID_HERE`):

   ```
   wrangler kv namespace create ALERTS
   ```

3. **Keys.** Make the server's key pair (needs Node 18 or newer):

   ```
   node make-keys.mjs
   ```

   - Paste the **public** key into `wrangler.toml` as `VAPID_PUBLIC_KEY`.
   - Store the **private** key as a secret (paste it when asked). Never commit it or put it in a file in the repo:

     ```
     wrangler secret put VAPID_PRIVATE_JWK
     ```

4. **Deploy.**

   ```
   wrangler deploy
   ```

   It prints the server's address, like `https://bradley-analytics-alerts.<your-subdomain>.workers.dev`.
   Opening it shows `{"ok":true,...}`.

5. **Connect the site.** In `docs/_config.yml` set:

   ```
   push_worker_url: "https://bradley-analytics-alerts.<your-subdomain>.workers.dev"
   push_public_key: "<the public key from step 3>"
   ```

   Commit and push. From then on, turning alerts on with the bell also subscribes the browser to the server, and the
   panel says "Alerts are on, even when the site is closed."

If the site is ever served from another address, add it to `ALLOWED_ORIGINS` in `wrangler.toml` and deploy again.

## How it works

- Every minute (`[triggers] crons`), the Worker reads ESPN's public NBA scoreboard for the day, compares it with what it
  saw last time (`seen` in KV) and works out the alerts in `src/alerts.js` — the same checks as `docs/assets/notify.js`,
  so keep the two in step if one changes.
- Each subscriber (`sub:<id>` in KV: the browser's push subscription and its alert choices) gets only the alerts they
  picked. Messages are encrypted for that browser and signed with the server's key (`src/webpush.js`, standard Web Push).
- A browser that turns alerts off, or that the push service says is gone, is removed.
- KV writes only happen when something changes (a subscription, or a game's state), so it stays well inside the free
  plan's limits.

## Files

- `src/index.js` — the Worker: `/subscribe`, `/unsubscribe`, and the once-a-minute check.
- `src/alerts.js` — what's worth an alert.
- `src/webpush.js` — encrypting and signing one push message (Web Crypto only, no packages).
- `make-keys.mjs` — makes the key pair.
- `wrangler.toml` — the Worker's settings.

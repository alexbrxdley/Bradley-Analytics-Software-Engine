// Makes the notification server's key pair (VAPID). Run once: node make-keys.mjs
// - The PUBLIC key goes in two places: worker/wrangler.toml (VAPID_PUBLIC_KEY) and docs/_config.yml (push_public_key).
// - The PRIVATE key is a secret: `npx wrangler secret put VAPID_PRIVATE_JWK` and paste it when asked. Don't commit it.
import { webcrypto as crypto } from "node:crypto";
const kp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const raw = new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey));
const jwk = await crypto.subtle.exportKey("jwk", kp.privateKey);
const b64u = (b) => Buffer.from(b).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
console.log("PUBLIC key (wrangler.toml VAPID_PUBLIC_KEY and docs/_config.yml push_public_key):\n" + b64u(raw) + "\n");
console.log("PRIVATE key (secret: npx wrangler secret put VAPID_PRIVATE_JWK):\n" + JSON.stringify({ kty: jwk.kty, crv: jwk.crv, x: jwk.x, y: jwk.y, d: jwk.d }));

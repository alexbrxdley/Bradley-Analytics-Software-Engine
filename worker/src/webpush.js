// Sending one Web Push message, with nothing but the Web Crypto API (it runs as-is on Cloudflare Workers and Node 18+):
// the message is encrypted for the browser that subscribed (RFC 8291, "aes128gcm") and signed as coming from this
// server (VAPID, RFC 8292).
const te = new TextEncoder();

export function b64uEncode(buf) {
  const b = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export function b64uDecode(str) {
  const s = str.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((str.length + 3) % 4);
  const bin = atob(s), out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function concat(...parts) {
  const n = parts.reduce((a, p) => a + p.length, 0), out = new Uint8Array(n);
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}
async function hmac(key, data) {
  const k = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, data));
}

// RFC 8291: encrypt `payload` (bytes) for a subscription's p256dh / auth keys
export async function encrypt(payload, p256dh, auth) {
  const uaPublic = b64uDecode(p256dh), authSecret = b64uDecode(auth);
  const local = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const asPublic = new Uint8Array(await crypto.subtle.exportKey("raw", local.publicKey));
  const uaKey = await crypto.subtle.importKey("raw", uaPublic, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: uaKey }, local.privateKey, 256));
  // IKM = HKDF(auth secret, shared secret, "WebPush: info" || 0 || ua public || as public)
  const prkKey = await hmac(authSecret, shared);
  const ikm = await hmac(prkKey, concat(te.encode("WebPush: info\0"), uaPublic, asPublic, new Uint8Array([1])));
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const prk = await hmac(salt, ikm);
  const cek = (await hmac(prk, concat(te.encode("Content-Encoding: aes128gcm\0"), new Uint8Array([1])))).slice(0, 16);
  const nonce = (await hmac(prk, concat(te.encode("Content-Encoding: nonce\0"), new Uint8Array([1])))).slice(0, 12);
  const key = await crypto.subtle.importKey("raw", cek, { name: "AES-GCM" }, false, ["encrypt"]);
  const plain = concat(payload, new Uint8Array([2]));                       // one record: the last-record delimiter
  const cipher = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, plain));
  const header = new Uint8Array(16 + 4 + 1 + asPublic.length);
  header.set(salt, 0);
  new DataView(header.buffer).setUint32(16, 4096);                          // record size
  header[20] = asPublic.length;
  header.set(asPublic, 21);
  return concat(header, cipher);
}

// RFC 8292: the signed token that says who's sending (ES256 JWT for the push service's origin)
const keyCache = new Map();
export async function vapidAuth(endpoint, publicKey, privateJwk, subject) {
  const aud = new URL(endpoint).origin;
  const exp = Math.floor(Date.now() / 1000) + 12 * 3600;
  const enc = (o) => b64uEncode(te.encode(JSON.stringify(o)));
  const unsigned = enc({ typ: "JWT", alg: "ES256" }) + "." + enc({ aud, exp, sub: subject });
  let key = keyCache.get(privateJwk);
  if (!key) {
    const jwk = typeof privateJwk === "string" ? JSON.parse(privateJwk) : privateJwk;
    key = await crypto.subtle.importKey("jwk", { kty: "EC", crv: "P-256", x: jwk.x, y: jwk.y, d: jwk.d, ext: true },
      { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
    keyCache.set(privateJwk, key);
  }
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, te.encode(unsigned));   // r || s, as JWS wants
  return "vapid t=" + unsigned + "." + b64uEncode(sig) + ", k=" + publicKey;
}

// send `message` (an object, sent as JSON) to one subscription; resolves to the push service's HTTP status
export async function sendPush(subscription, message, { publicKey, privateJwk, subject, ttl = 3600, fetchImpl = fetch } = {}) {
  const body = await encrypt(te.encode(JSON.stringify(message)), subscription.keys.p256dh, subscription.keys.auth);
  const res = await fetchImpl(subscription.endpoint, {
    method: "POST",
    headers: {
      Authorization: await vapidAuth(subscription.endpoint, publicKey, privateJwk, subject),
      "Content-Encoding": "aes128gcm",
      "Content-Type": "application/octet-stream",
      TTL: String(ttl),
      Urgency: "high"
    },
    body
  });
  return res.status;
}

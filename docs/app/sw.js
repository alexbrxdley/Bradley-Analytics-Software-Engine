// The app's helper in the phone (needed for "install app" on Android). It keeps nothing old: every page and score comes
// fresh from the internet, so the app always matches the website.
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function () {});

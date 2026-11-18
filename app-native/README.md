# The Bradley Analytics app

The app is the page **bradley-analytics.com/app/**. The files for that page are in `docs/app/`. This folder,
`app-native/`, is the small native shell that turns that page into a real App Store and Google Play app. Because the
shell just opens the live page, **updating the website updates the app**. You only rebuild the store app when the
shell itself changes: a new icon, a new native feature, or a new version number.

## Test it now (no store needed)
- **iPhone:** open `bradley-analytics.com/app/` in Safari, tap Share, then **Add to Home Screen**. It opens full screen
  like an app.
- **Android:** open the same address in Chrome, open the menu, then tap **Install app**. Or build a real Android test app
  with `build-android.yml` (see the note at the top of that file).

## Putting it in the stores
1. **Accounts:** Apple Developer Program costs $99 a year (developer.apple.com). Google Play Console costs $25 once
   (play.google.com/console).
2. **Build:**
   - Android builds on any computer with Android Studio: `npm install`, `npx cap add android`, `npx cap open android`,
     then Build > Generate Signed Bundle.
   - iOS needs a Mac with Xcode. With a Windows computer, use a cloud build service such as Codemagic or Ionic Appflow.
     Connect it to this GitHub repo and it builds and uploads the iPhone app for you.
3. **Test with real people:** TestFlight (Apple) and Internal testing (Google Play) send the app to your own testers
   before anyone else sees it.
4. **Submit:** you need screenshots, a description, a privacy policy page and an age rating. Apple reviews every
   version, usually in 1–3 days.

Apple turns down apps that are "just a website". Before submitting, the shell should use a few native features:
push notifications for game alerts and newsletters, haptics, and the tilting floor (already built). The plugins are
already listed in `package.json`.

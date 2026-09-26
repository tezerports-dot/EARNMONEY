# Building and releasing the APK

The app is shared as an APK file and a download link, not through a store (yet). This page covers the signing key, building a release, publishing it, and forcing updates.

## Before the first release

### 1. Replace the placeholder domain

The server builds referral links from its own address, and the app only accepts links on its `WEB_HOST`. Use your real domain (the same one as `FF_PUBLIC_BASE_URL` in [SETUP.md](SETUP.md)) in:

- `mobile/config/prod.json`: `API_BASE_URL` (`https://your-domain`) and `WEB_HOST` (`your-domain`). A test fails if their hosts differ.
- `mobile/android/app/build.gradle.kts`: the prod flavor's `webHost` default (`futurefashion.example`). Or pass it at build time with `--android-project-arg webHost=your-domain`.

The Android app id is `com.futurefashion.app`. Change it now if you want a different one. It can't change after users install the app.

### 2. Create the signing key, once

Every update must be signed with the same key. **If the key is lost, installed apps can't be updated**: every user would have to uninstall, and their app data would be lost. Their account and rewards stay safe on the server.

```bash
keytool -genkeypair -v -keystore futurefashion-release.jks -alias futurefashion \
  -keyalg RSA -keysize 4096 -validity 10000
```

Keep the `.jks` file and both passwords in at least two safe places, such as a password manager and an offline copy. Never commit them.

### 3. Tell the build where the key is

Create `mobile/android/key.properties`. Git ignores it.

```properties
storeFile=/absolute/path/to/futurefashion-release.jks
storePassword=…
keyAlias=futurefashion
keyPassword=…
```

Or set `FF_KEYSTORE_PATH`, `FF_KEYSTORE_PASSWORD`, `FF_KEY_ALIAS` and `FF_KEY_PASSWORD` as environment variables. Without either, release builds are signed with the debug key and the build log warns you. Those builds are for testing only.

### 4. Enable App Links

Referral links (`https://your-domain/r/CODE`) open the app directly when Android can verify that the domain belongs to the app. Print the key's fingerprint:

```bash
keytool -list -v -keystore futurefashion-release.jks -alias futurefashion | grep SHA256
```

Put it in the server's `.env` as `FF_ANDROID_CERT_SHA256=["AB:CD:…"]` and restart (`docker compose up -d`). The server then publishes it at `/.well-known/assetlinks.json`.

### 5. Ads (optional)

Ads are off until you switch them on in the admin panel. If you want them, create an AdMob app and ad units. Put the unit ids in `config/prod.json` (`ADMOB_BANNER_ID`, `ADMOB_INTERSTITIAL_ID`, `ADMOB_REWARDED_ID`), and pass the AdMob app id with `--android-project-arg admobAppId=ca-app-pub-…~…` or `FF_ADMOB_APP_ID`. Without them the build uses Google's test ads. Never switch ads on in the admin panel for a build that only has test ids.

## Building a release

1. Raise the version in `mobile/pubspec.yaml`. `1.0.1+2` means version name 1.0.1 and version code 2. The code must go up every release, or Android refuses the update.
2. Build:

   ```bash
   cd mobile
   flutter build apk --release --flavor prod --dart-define-from-file=config/prod.json
   ```

   The APK is `build/app/outputs/flutter-apk/app-prod-release.apk`, about 59 MB. It contains code for all common phone types, which keeps sharing simple: one file works everywhere.
3. Check it's signed with your key, not the debug key:

   ```bash
   $ANDROID_HOME/build-tools/<version>/apksigner verify --print-certs build/app/outputs/flutter-apk/app-prod-release.apk
   ```

   The certificate must be yours, not `CN=Android Debug`.
4. Install it on a few real phones before sharing it. Try signup, Telegram verification, sharing, and a referral link opened with the app installed and without it.

The `dev` and `staging` flavors install alongside the real app (`com.futurefashion.app.dev` / `.staging`) and use `config/dev.json` / `config/staging.json`.

## Publishing

1. Upload the APK to HTTPS storage. A Cloudflare R2 bucket with a custom domain works well: storage is cheap and downloads are free. Give each file a versioned name, such as `futurefashion-1.0.1.apk`.
2. In the admin panel, **Settings → APK download URL**: paste the file's URL. `https://your-domain/download` now redirects there. The referral landing page and the app's share message use that link.
3. Users also share the installed app itself (next section). That needs no hosting at all.

## How "Share App + Referral" works

The button always sends the APK file itself, never a download link:

1. The app copies its own installed APK into its cache. It needs no storage permission; it reads only its own package file.
2. The sharer's referral code goes into the copy's APK Signing Block, as one extra entry (`mobile/android/app/src/main/kotlin/com/futurefashion/app/ApkReferral.kt`). Android's v2/v3 signatures don't cover extra entries there, and Android ignores entries it doesn't know. So the copy installs like the original, has the same signing certificate, and takes your future updates.
3. Android's share sheet sends the file (WhatsApp, Telegram, Bluetooth, Nearby Share, Xender…) with a short message carrying the code and the referral link.
4. On the friend's phone, the app reads the code from the APK it was installed from, on its first launch, and fills it in at signup. This works even when the file travelled without the message. The friend can see and change the code, and the server checks it like any typed code.

If a phone can't attach the file (an app installed from a store in parts, or a full phone), the app says so and offers to send the referral link instead. It never swaps the file for a link on its own.

`ApkReferralTest` checks all of this with Google's own APK verifier (`apksig`, the library behind `apksigner`). Check a real build the same way:

```bash
cd mobile/android
./gradlew :app:testProdDebugUnitTest -PrealApk=$PWD/../build/app/outputs/flutter-apk/app-prod-release.apk
```

## Forcing an update

When an old version must stop working (say, after an API change), set **Settings → Minimum app version** to the new version. Older apps then show an "Update required" screen with the download link. Publish the new APK first.

## CI builds

GitHub Actions builds a prod release APK on every push (`.github/workflows/ci.yml`). The workflow has no signing key, so that APK is debug-signed. Use it only for testing, never share it. Users who installed a debug-signed APK can't update to your real one without uninstalling first.

## Later: Google Play and the App Store

The code is structured to be publishable. When you're ready:

- **Google Play:** build an app bundle (`flutter build appbundle --flavor prod --dart-define-from-file=config/prod.json`) and use Play App Signing. Fill in the Data safety form: phone number, Telegram id and bank details, all sent over HTTPS, with bank numbers encrypted at rest. Link the privacy policy, and review Play's policies on financial features and referral rewards. The developer account costs $25 once.
- **App Store:** the Flutter code is shared, but an iOS project, an Apple developer account ($99 a year) and Apple's review rules on rewards are needed first.

# BISNU-X Android client

This client is maintained and released as an Android APK. Web, iOS, and desktop releases are not supported.

## Requirements

- Flutter 3.47 or compatible
- Android SDK and Android Studio
- A stable public HTTPS URL for the BISNU-X FastAPI backend

The Android package is `app.bisnux.mobile`. Users register and sign in with a BISNU-X account ID in the form `username#bisnu-x.com` and a password. This suffix is an account identifier, not an email address or mailbox; Google sign-in is not used. Registration, login, and conversation history are provided by the backend. Passwords are scrypt-hashed on the server; the Android app stores only the bearer token in secure storage. There is no email/phone password reset, so users must keep their password safe.

For backend deployment, durable database setup, and runtime secrets, see the [production deployment guide](../DEPLOYMENT.md).

## Run on Android

For an Android emulator and a local development backend:

```powershell
flutter pub get
flutter run --dart-define=BISNU_API_URL=http://10.0.2.2:8000
```

`10.0.2.2` is the Android emulator's host-loopback address. A physical phone needs a reachable development-server address. Debug builds permit cleartext HTTP for local development; release builds require HTTPS.

## Build a signed release APK

Configure `BISNU_API_URL` as a stable HTTPS backend before building:

```powershell
flutter build apk --release --target-platform android-arm64 --dart-define=BISNU_API_URL=https://YOUR_STABLE_API_HOST
```

The output path is `build/app/outputs/flutter-apk/app-release.apk`. Do not use a Cloudflare Quick Tunnel URL for a published build: Quick Tunnel hostnames are temporary and can stop resolving.

Before distributing an online release:

1. Confirm `GET /health` and `GET /api/status` return HTTP 200 at the configured HTTPS host.
2. Confirm the gateway is configured in `/health`, then exercise real account registration/login, chat, history restoration, and live search on a physical Android device.
3. Verify the APK signature and application ID. Never call the APK fully working based solely on a successful build.

Release signing reads `key.properties` from the repository root. Keep it and its keystore private and backed up. An archived copy in this workspace contains hard-coded upload-key signing credentials; treat the current upload key as compromised. Rotate or replace it before store publishing.

## Android scanner

The Android scanner uses on-device Latin and Devanagari text recognition. The image stays on the device; OCR text is sent to chat only after the user taps Analyze. Server-side image recognition is not configured.

To build and verify a signed ARM64 release after backend deployment:

1. Generate a new upload keystore and update the ignored root `key.properties`. For example, run `keytool -genkeypair -keystore bisnux-upload-key.jks -alias bisnux-upload -keyalg RSA -keysize 4096 -validity 10000`; enter passwords at the prompts, not in the command line. Keep the keystore and properties file private.
2. If the app is already on Play, follow Play Console's upload-key rotation flow.
3. From the Flutter directory, run `.\build-release.ps1 -ApiUrl "https://YOUR_API_HOST" -ConfirmSigningKeyIsRotated`.

The script requires the Flutter SDK, local signing configuration, and Android SDK `apksigner`; it rejects an HTTP backend URL or an unacknowledged old signing key.

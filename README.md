# BISNU-X

BISNU-X contains a FastAPI backend and an Android-only Flutter client. The backend can orchestrate configured Qwen, Llama, and optional BISNU model weights; the application does not bundle those weights or claim performance superior to other AI systems. Model availability, speed, and quality depend on the configured checkpoints and server hardware.

## Local setup

Use Python 3.11 or newer. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a random `BISNU_JWT_SECRET` of at least 32 bytes in `.env` before testing authenticated routes. Configure model paths/IDs and features there as needed. Never commit `.env` or paste server secrets into a public issue or chat.

Start the API:

```powershell
python run_web.py
```

The API listens at <http://127.0.0.1:8000>; interactive API documentation is at <http://127.0.0.1:8000/docs>. `GET /health` reports configured capabilities; it does not prove that model weights are downloaded or that external services are production-ready. If Flutter web has been built, the same API serves `flutter/build/web` at `/`.

Optional dependencies:

```powershell
python -m pip install -r requirements-model.txt
python -m pip install -r requirements-web.txt
```

The model group installs Transformers/PyTorch. Install a PyTorch build compatible with the server's CUDA hardware if using a GPU. Model weights must be separately obtained under their own licenses. Configure `QWEN_MODEL`, `LLAMA_MODEL`, and optionally `BISNU_MODEL`; BISNU is an orchestration layer unless you provide actual BISNU weights. `DEVICE=auto` selects an available accelerator or CPU. CPU inference may be very slow.

## Android and web client

See [Flutter setup and release notes](flutter/README.md). The Android release requires a private upload keystore and local `key.properties`; the example key file must never be checked in. Provide the deployed HTTPS API URL at build time. Web, iOS, and desktop releases are not supported.

## Production deployment

The recommended Railway + Neon production architecture, environment variables,
cost assumptions, deployment procedure, and Render migration steps are in
[DEPLOYMENT.md](DEPLOYMENT.md). The API uses PostgreSQL when `DATABASE_URL` is
set and can be configured to refuse ephemeral SQLite in a deployed service.
Keep provider credentials in Railway's secret environment variables. The
workspace has not yet been deployed to Railway; production credentials,
database, and signing material still need to be configured.

## Authentication and payments

Users register and sign in with a unique BISNU-X account ID in the form `username#bisnu-x.com` and a password. The suffix is an account identifier only; it is not an email address or mailbox, and Google sign-in is not used. Passwords are scrypt-hashed on the backend; only the short-lived bearer token is stored in Android secure storage. There is no email/phone password reset, so users must keep their password safe. Set `BISNU_JWT_SECRET` to a cryptographically random value of at least 32 bytes and use HTTPS for a public deployment.

Real Razorpay recurring subscriptions require server-side `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`, plus Premium/Ultra plan IDs created in the Razorpay Dashboard. The server checks that each selected plan is monthly, interval 1, and INR before creating checkout. Configure the webhook URL as `https://YOUR_HOST/v1/payment/webhook` and subscribe it to the subscription activation, charge, pause/halt, cancellation, and completion events supported by the account. Use Razorpay test mode first. An activation event alone does not grant access: a signed `subscription.charged` event must include a captured payment for the server-created subscription at the exact configured plan amount, and the subscription must have a valid paid-through date. Client redirects or client-provided payment claims do not grant access. The configured `RAZORPAY_SUBSCRIPTION_TOTAL_COUNT` limits the number of billing cycles; it is not an unlimited subscription.

Do not expose the API directly to the public internet without HTTPS termination, firewalling, monitoring, backups, and appropriate rate limiting. The in-process request limiter is not a distributed production abuse-control system. Store secrets in the deployment's secret manager, not in source control.

## Implemented capabilities and limits

- Authenticated chat with conversation history and optional saved-memory context.
- Qwen/Llama/BISNU model selection when corresponding models are configured; live search is separately configurable.
- Android image capture/gallery scan with on-device Latin and Devanagari OCR. Scanner access is Premium-gated. The image stays on-device; OCR text reaches chat only when the user taps Analyze. No server-side image-understanding model is configured by default.
- Razorpay monthly recurring plan checkout and webhook-confirmed entitlement.
- Paid plans and Premium scanner access remain Coming Soon until the complete Razorpay secret set is configured; secrets alone never grant paid access.
- Video generation/analysis is not implemented and is explicitly unavailable. Do not advertise it as a working feature.

## Tests

```powershell
python -m unittest tests.test_payments_active -v
```

This runs focused tests for signed Razorpay webhook validation, server-created plan matching, paid-through dates, event deduplication/entitlement, PostgreSQL SQL translation and persistent-database safeguards, Premium scanner authorization, and authenticated Android API contracts. The older full suite (`python -m unittest discover -s tests -v`) currently contains imports for package paths that are not present in this active backend; it fails during test collection and is not a passing project-wide test run.

Flutter checks (run from `flutter`):

```powershell
flutter pub get
flutter analyze
flutter test
```

## Honest capability claims

The project does not ship proprietary model weights, Google/Razorpay credentials, a hosted production server, or Windows C++ build tools. Configure, license, deploy, and evaluate those components before release. A small local test or benchmark does not establish superiority to GPT-class or other proprietary systems.

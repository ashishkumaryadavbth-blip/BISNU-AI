from __future__ import annotations

import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / ("PAYMENT_PATCH_BACKUP_" + datetime.now().strftime("%Y%m%d_%H%M%S"))

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")

def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8")

def backup(path: Path) -> None:
    if path.exists():
        dest = BACKUP / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find patch anchor: {label}")
    return text.replace(old, new, 1)

# CONFIG
p = ROOT / "bisnu_x" / "config.py"
backup(p)
s = read(p)
s = replace_once(s, """class Settings:
    app_name = "BISNU-X"

    version = "7.0.0"
""", """class Settings:
    app_name = "BISNU-X"

    version = "7.0.0"

    project_root = ROOT
""", "Settings.project_root")
s = replace_once(s, """    razorpay_ultra_plan_id = os.getenv("RAZORPAY_ULTRA_PLAN_ID", "")
    razorpay_subscription_total_count = env_int(
""", """    razorpay_ultra_plan_id = os.getenv("RAZORPAY_ULTRA_PLAN_ID", "")

    payment_qr_path = os.getenv(
        "RAZORPAY_PAYMENT_QR_PATH",
        "payment/razorpay-qr.png",
    ).strip()

    razorpay_subscription_total_count = env_int(
""", "payment QR setting")
write(p, s)

# PAYMENTS
p = ROOT / "bisnu_x" / "payments.py"
backup(p)
s = read(p)
a = s.index("def payments_available")
b = s.index("def _require_razorpay")
s = s[:a] + """def payment_qr_path():
    from pathlib import Path

    configured = str(settings.payment_qr_path or "").strip()
    if not configured:
        return None

    path = Path(configured)
    if not path.is_absolute():
        path = Path(settings.project_root) / path
    return path


def payment_qr_configured() -> bool:
    path = payment_qr_path()
    try:
        return bool(path and path.is_file() and path.stat().st_size > 0)
    except OSError:
        return False


def _gateway_ready() -> bool:
    return bool(
        settings.razorpay_key_id
        and settings.razorpay_key_secret
        and settings.razorpay_webhook_secret
    )


def premium_available() -> bool:
    return bool(
        _gateway_ready()
        and settings.razorpay_premium_plan_id
        and payment_qr_configured()
    )


def ultra_available() -> bool:
    return bool(
        _gateway_ready()
        and settings.razorpay_ultra_plan_id
        and payment_qr_configured()
    )


def payments_available() -> bool:
    return bool(
        _gateway_ready()
        and settings.razorpay_premium_plan_id
        and settings.razorpay_ultra_plan_id
    )


def payment_status() -> dict[str, Any]:
    return {
        "premium": premium_available(),
        "ultra": ultra_available(),
        "qr_configured": payment_qr_configured(),
        "gateway_configured": _gateway_ready(),
        "premium_plan_configured": bool(settings.razorpay_premium_plan_id),
        "ultra_plan_configured": bool(settings.razorpay_ultra_plan_id),
    }


""" + s[b:]
a = s.index("def require_payment_configuration")
b = s.index("def require_plan", a)
s = s[:a] + """def require_payment_configuration(plan: str = "PREMIUM") -> None:
    plan = plan.upper()
    ready = premium_available() if plan == "PREMIUM" else ultra_available()
    if not ready:
        raise HTTPException(
            status_code=503,
            detail=f"{plan.title()} subscriptions are coming soon.",
        )


def require_gateway_configuration() -> None:
    if not _gateway_ready():
        raise HTTPException(
            status_code=503,
            detail="Razorpay gateway is not configured.",
        )


""" + s[b:]
write(p, s)

# APP
p = ROOT / "bisnu_x" / "app.py"
backup(p)
s = read(p)
s = replace_once(s, "from fastapi.responses import JSONResponse",
                 "from fastapi.responses import FileResponse, JSONResponse",
                 "FileResponse import")

old = """@app.get("/v1/me/subscription")
def subscription_status(
    user=Depends(current_user),
):
    return {
        "plan": user.get("plan", "FREE"),
        "subscription": db.get_user_subscription(
            user["id"],
        ),
        "available": payments.payments_available(),
    }


"""
new = """@app.get("/v1/me/subscription")
def subscription_status(
    user=Depends(current_user),
):
    payment_state = payments.payment_status()
    return {
        "plan": user.get("plan", "FREE"),
        "subscription": db.get_user_subscription(user["id"]),
        "available": payment_state["premium"],
        "premium_available": payment_state["premium"],
        "ultra_available": payment_state["ultra"],
        "qr_configured": payment_state["qr_configured"],
        "qr_url": "/v1/payment/qr" if payment_state["qr_configured"] else None,
    }


@app.get("/v1/payment/qr")
def payment_qr():
    path = payments.payment_qr_path()
    if not path or not path.is_file() or path.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="Payment QR is not configured.")

    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(path.suffix.lower())
    if not media_type:
        raise HTTPException(
            status_code=500,
            detail="Payment QR must be PNG, JPG, JPEG, or WEBP.",
        )

    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )


"""
s = replace_once(s, old, new, "subscription endpoint")
s = replace_once(s, """    payments.require_payment_configuration()
    return payments.create_subscription(
""", """    payments.require_payment_configuration(payload.plan)
    return payments.create_subscription(
""", "subscription creation gate")
s = replace_once(s, """    payments.require_payment_configuration()
    return payments.cancel_subscription(
""", """    payments.require_gateway_configuration()
    return payments.cancel_subscription(
""", "subscription cancellation gate")

s = s.replace('"premium_available": payments.payments_available(),',
              '"premium_available": payments.premium_available(),')
s = s.replace('"premium": payments.payments_available(),',
              '"premium": payments.premium_available(),')
s = s.replace('"payments": payments.payments_available(),',
              '"payments": payments.premium_available(),')
s = s.replace('"ultra": payments.payments_available(),',
              '"ultra": payments.ultra_available(),')
s = s.replace('if payments.payments_available()',
              'if payments.premium_available()')
write(p, s)

# FLUTTER
p = ROOT / "flutter" / "lib" / "screens" / "subscription_screen.dart"
backup(p)
write(p, r"""import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/api_service.dart';

class SubscriptionScreen extends StatefulWidget {
  const SubscriptionScreen({super.key, required this.api});

  final ApiService api;

  @override
  State<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<SubscriptionScreen> {
  Map<String, dynamic>? _subscription;
  String? _qrUrl;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.api.getSubscription();
      if (mounted) {
        final rawQr = result['qr_url']?.toString();
        setState(() {
          _subscription = result;
          _qrUrl = rawQr == null || rawQr.isEmpty ? null : rawQr;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start(String plan) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.api.createSubscription(plan);
      final checkout = Uri.parse(result['checkout_url'].toString());
      if (checkout.scheme != 'https' ||
          !await launchUrl(checkout, mode: LaunchMode.externalApplication)) {
        throw const ApiException('Could not open Razorpay checkout.');
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Checkout opened. Access activates only after Razorpay confirms '
              'the subscription to the server.',
            ),
          ),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancel() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cancel renewal?'),
        content: const Text(
          'Razorpay will schedule cancellation at the end of the current cycle. '
          'Current access remains governed by the verified subscription period.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep plan'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Cancel renewal'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.cancelSubscription();
      await _refresh();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final current = _subscription?['plan']?.toString() ?? 'FREE';
    final providerStatus =
        (_subscription?['subscription'] as Map<String, dynamic>?)?['status']
            ?.toString();
    final premiumAvailable =
        _subscription?['premium_available'] == true ||
        _subscription?['available'] == true;
    final ultraAvailable = _subscription?['ultra_available'] == true;
    final qrUrl = _qrUrl;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Subscriptions'),
        actions: [
          IconButton(
            tooltip: 'Refresh payment status',
            onPressed: _busy ? null : _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Card(
              child: ListTile(
                leading: const Icon(Icons.verified_user_outlined),
                title: Text('Current plan: $current'),
                subtitle: Text(
                  providerStatus == null
                      ? 'No active Razorpay subscription'
                      : 'Razorpay status: $providerStatus',
                ),
              ),
            ),
            const SizedBox(height: 16),

            if (premiumAvailable && qrUrl != null) ...[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Payment QR',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'QR is a payment aid only. A QR scan never grants Premium '
                        'by itself; the server must receive a valid Razorpay '
                        'webhook for the subscription it created.',
                      ),
                      const SizedBox(height: 12),
                      Center(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: Image.network(
                            '${widget.api.baseUrl}$qrUrl',
                            width: 220,
                            height: 220,
                            fit: BoxFit.contain,
                            errorBuilder: (_, __, ___) => const SizedBox(
                              height: 80,
                              child: Center(
                                child: Text('Payment QR could not be loaded.'),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],

            for (final plan in const ['PREMIUM', 'ULTRA'])
              Builder(
                builder: (context) {
                  final planAvailable =
                      plan == 'PREMIUM' ? premiumAvailable : ultraAvailable;
                  return Card(
                    child: ListTile(
                      title: Text(plan),
                      subtitle: Text(
                        planAvailable
                            ? 'Monthly recurring plan. Final amount and billing terms '
                              'are shown on Razorpay-hosted checkout.'
                            : 'Coming Soon',
                      ),
                      trailing: FilledButton(
                        onPressed: !planAvailable ||
                                _busy ||
                                current == plan
                            ? null
                            : () => _start(plan),
                        child: Text(
                          !planAvailable
                              ? 'Coming Soon'
                              : current == plan
                                  ? 'Active'
                                  : 'Subscribe',
                        ),
                      ),
                    ),
                  );
                },
              ),

            if (providerStatus == 'active')
              OutlinedButton.icon(
                onPressed: _busy ? null : _cancel,
                icon: const Icon(Icons.cancel_outlined),
                label: const Text('Cancel renewal'),
              ),

            if (_busy) ...[
              const SizedBox(height: 16),
              const Center(child: CircularProgressIndicator()),
            ],

            if (_error case final error?) ...[
              const SizedBox(height: 12),
              SelectableText(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],

            const SizedBox(height: 12),
            Text(
              premiumAvailable
                  ? 'Paid access is never activated from a browser callback or '
                      'QR scan. BISNU-X activates the plan only after a valid '
                      'Razorpay webhook is verified against a server-created '
                      'subscription.'
                  : 'Premium is Coming Soon until the server has the Razorpay '
                      'key ID, key secret, webhook secret, Premium plan ID, '
                      'and a real payment QR image.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
""")

# ENV + GITIGNORE + QR instructions
p = ROOT / ".env.example"
backup(p)
s = read(p)
if "RAZORPAY_PAYMENT_QR_PATH" not in s:
    s += "\n# Premium payment readiness gate\nRAZORPAY_PAYMENT_QR_PATH=payment/razorpay-qr.png\n"
write(p, s)

p = ROOT / ".gitignore"
backup(p)
s = read(p)
if "payment/razorpay-qr.*" not in s:
    s += "\npayment/razorpay-qr.*\n"
write(p, s)

(ROOT / "payment").mkdir(exist_ok=True)
write(ROOT / "payment" / "README.txt", """Put the REAL payment QR image here:
payment/razorpay-qr.png

Supported: PNG, JPG, JPEG, WEBP.

A placeholder QR does not count. Premium stays Coming Soon until the
file exists and has non-zero size.

The QR never grants Premium directly. Premium is granted only after
a valid Razorpay webhook for a server-created subscription.
""")

print("PATCH COMPLETE")
print("Backup:", BACKUP)
print("Add your REAL QR at: payment/razorpay-qr.png")

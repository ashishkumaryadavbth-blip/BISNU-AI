param(
    [string]$ProjectRoot = (Get-Location).Path,
    [string]$RazorpayPaymentLink = "PASTE_FULL_RAZORPAY_PAYMENT_LINK_HERE"
)

$ErrorActionPreference = 'Stop'

function Write-Utf8([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Read-Utf8([string]$Path) {
    return [System.IO.File]::ReadAllText($Path)
}

function Replace-Once([string]$Path, [string]$Pattern, [string]$Replacement, [string]$Name) {
    $text = Read-Utf8 $Path
    $new = [regex]::Replace($text, $Pattern, $Replacement, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($new -eq $text) { throw "Could not patch $Name in $Path" }
    Write-Utf8 $Path $new
}

function Remove-Regex([string]$Path, [string]$Pattern, [string]$Name) {
    $text = Read-Utf8 $Path
    $new = [regex]::Replace($text, $Pattern, '', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($new -eq $text) { Write-Host "WARN: $Name not found in $Path" }
    Write-Utf8 $Path $new
}

$root = (Resolve-Path $ProjectRoot).Path
$backend = Join-Path $root 'bisnu_x'
$flutter = Join-Path $root 'flutter'
$tests = Join-Path $root 'tests'

if (!(Test-Path (Join-Path $root 'bisnu_x/app.py'))) { throw "BISNU-X project not found: $root" }
if (!(Test-Path (Join-Path $flutter 'pubspec.yaml'))) { throw "Flutter project not found: $flutter" }

# Backup source files before modifying anything.
$backup = Join-Path $root ("backup_before_complete_update_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$backupFiles = @(
    'bisnu_x/app.py',
    'bisnu_x/payments.py',
    'bisnu_x/config.py',
    'flutter/pubspec.yaml',
    'flutter/lib/services/api_service.dart',
    'flutter/lib/screens/chat_screen.dart',
    'flutter/lib/screens/subscription_screen.dart',
    'README.md',
    '.env.example',
    'tests/test_payments_active.py'
)
foreach ($rel in $backupFiles) {
    $src = Join-Path $root $rel
    if (Test-Path $src) {
        $dst = Join-Path $backup $rel
        New-Item -ItemType Directory -Path (Split-Path $dst) -Force | Out-Null
        Copy-Item $src $dst -Force
    }
}

# ---------------------------------------------------------------------------
# 1) REMOVE THE SCANNER COMPLETELY FROM THE BACKEND
# ---------------------------------------------------------------------------
$appPy = Join-Path $backend 'app.py'
$app = Read-Utf8 $appPy
$app = $app -replace '(?m)^\s*File,\r?\n', ''
$app = $app -replace '(?m)^\s*UploadFile,\r?\n', ''
$app = $app -replace '(?m)^from bisnu_x\.scanner import save_image\r?\n', ''
$app = [regex]::Replace($app, '(?ms)^@app\.get\("/v1/scanner/access"\).*?(?=^@app\.get\("/v1/me/subscription")', '')
$app = [regex]::Replace($app, '(?ms)^# ============================================================\r?\n# SCANNER\r?\n# ============================================================\r?\n.*?(?=^# ============================================================\r?\n# ADMIN MODEL STATUS)', '')
$app = $app -replace '(?m)^\s*"scanner_upload": True,\r?\n', ''
$app = [regex]::Replace($app, '(?m)^        "payment_link_available": bool\(settings\.razorpay_key_id and settings\.razorpay_key_secret and settings\.razorpay_webhook_secret\),$', '        "payment_link_available": bool(settings.razorpay_key_id and settings.razorpay_key_secret and settings.razorpay_webhook_secret),
        "static_payment_link_available": bool(settings.razorpay_premium_payment_link),')
Write-Utf8 $appPy $app

# ---------------------------------------------------------------------------
# 2) REMOVE SCANNER FLAGS FROM PAYMENT PLANS
# ---------------------------------------------------------------------------
$paymentsPy = Join-Path $backend 'payments.py'
$pay = Read-Utf8 $paymentsPy
$pay = $pay -replace '(?m)^\s*"scanner": (True|False),\r?\n', ''
Write-Utf8 $paymentsPy $pay

# ---------------------------------------------------------------------------
# 3) MAKE THE EXISTING PREMIUM PAYMENT LINK A SAFE FALLBACK.
#    Dynamic server-created links remain preferred when Razorpay API keys are set.
# ---------------------------------------------------------------------------
$pay = Read-Utf8 $paymentsPy
$old = @'
def create_premium_payment_link(user_id: str) -> dict[str, Any]:
    """Create a one-time ₹399 Premium Payment Link tied to this user.

    The user id is stored in the Payment Link reference_id/notes so the
    signed payment_link.paid webhook can safely grant the entitlement.
    """
    _require_razorpay(webhook=False)
'@
$new = @'
def create_premium_payment_link(user_id: str) -> dict[str, Any]:
    """Return a real Razorpay Premium link.

    Preferred mode is a server-created per-user link, because the signed
    payment_link.paid webhook can then map the payment to the authenticated
    user. A Dashboard-created static link is supported as a fallback for
    checkout/testing, but a static link must not be used for automatic user
    entitlement unless its webhook can identify the user.
    """
    static_link = settings.razorpay_premium_payment_link.strip()
    if static_link and static_link.startswith("https://"):
        return {
            "payment_link_id": "static-dashboard-link",
            "payment_url": static_link,
            "amount": settings.razorpay_premium_payment_amount,
            "currency": "INR",
            "plan": "PREMIUM",
            "duration_days": settings.razorpay_premium_payment_days,
            "activation_mode": "webhook-or-manual-verification",
        }

    _require_razorpay(webhook=False)
'@
if ($pay -notlike "*$old*") { throw 'Could not find create_premium_payment_link block.' }
$pay = $pay.Replace($old, $new)
Write-Utf8 $paymentsPy $pay

# ---------------------------------------------------------------------------
# 4) FLUTTER: DELETE SCANNER UI + REMOVE ITS CHAT BUTTON
# ---------------------------------------------------------------------------
$chatPy = Join-Path $flutter 'lib/screens/chat_screen.dart'
$chat = Read-Utf8 $chatPy
$chat = $chat -replace '(?m)^import ''scanner_screen\.dart'';\r?\n', ''
$chat = [regex]::Replace($chat, '(?ms)^\s*Future<void> _openScanner\(\) async \{.*?^\s*\}\r?\n\r?\n(?=\s*Future<void> _openSubscriptions)', '')
$chat = [regex]::Replace($chat, '(?ms)^\s*IconButton\(\s*tooltip: ''Scan document'',.*?\),\r?\n', '')
Write-Utf8 $chatPy $chat

$apiPy = Join-Path $flutter 'lib/services/api_service.dart'
$api = Read-Utf8 $apiPy
$api = [regex]::Replace($api, '(?ms)^\s*Future<void> checkScannerAccess\(\) async \{.*?^\s*\}\r?\n\r?\n(?=\s*Future<Map<String, dynamic>> createPremiumPaymentLink)', '')
Write-Utf8 $apiPy $api

$scannerFile = Join-Path $flutter 'lib/screens/scanner_screen.dart'
if (Test-Path $scannerFile) { Remove-Item $scannerFile -Force }
$scannerBackend = Join-Path $backend 'scanner.py'
if (Test-Path $scannerBackend) { Remove-Item $scannerBackend -Force }

# ---------------------------------------------------------------------------
# 5) FLUTTER DEPENDENCIES: REMOVE CAMERA/OCR PACKAGES.
# ---------------------------------------------------------------------------
$pubspec = Join-Path $flutter 'pubspec.yaml'
$pub = Read-Utf8 $pubspec
$pub = $pub -replace '(?m)^\s*image_picker:\s*[^\r\n]+\r?\n', ''
$pub = $pub -replace '(?m)^\s*google_mlkit_text_recognition:\s*[^\r\n]+\r?\n', ''
Write-Utf8 $pubspec $pub

# ---------------------------------------------------------------------------
# 6) STATIC PAYMENT LINK CONFIGURATION.
# ---------------------------------------------------------------------------
$envExample = Join-Path $root '.env.example'
if (Test-Path $envExample) {
    $env = Read-Utf8 $envExample
    if ($env -match '(?m)^RAZORPAY_PREMIUM_PAYMENT_LINK=.*$') {
        $env = [regex]::Replace($env, '(?m)^RAZORPAY_PREMIUM_PAYMENT_LINK=.*$', "RAZORPAY_PREMIUM_PAYMENT_LINK=$RazorpayPaymentLink")
    } else {
        $env += "`r`n# Dashboard-created Razorpay Payment Link fallback`r`nRAZORPAY_PREMIUM_PAYMENT_LINK=$RazorpayPaymentLink`r`n"
    }
    Write-Utf8 $envExample $env
}

$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    $env = Read-Utf8 $envFile
    if ($env -match '(?m)^RAZORPAY_PREMIUM_PAYMENT_LINK=.*$') {
        $env = [regex]::Replace($env, '(?m)^RAZORPAY_PREMIUM_PAYMENT_LINK=.*$', "RAZORPAY_PREMIUM_PAYMENT_LINK=$RazorpayPaymentLink")
    } else {
        $env += "`r`nRAZORPAY_PREMIUM_PAYMENT_LINK=$RazorpayPaymentLink`r`n"
    }
    Write-Utf8 $envFile $env
}

# ---------------------------------------------------------------------------
# 7) SUBSCRIPTION SCREEN: PREMIUM IS ₹399 AND OPENS RAZORPAY.
# ---------------------------------------------------------------------------
$subFile = Join-Path $flutter 'lib/screens/subscription_screen.dart'
$sub = Read-Utf8 $subFile
$sub = [regex]::Replace($sub, "(?ms)\s*final paymentsAvailable = .*?;\r?\n\s*final paymentLinkReady = .*?;", @"
    final paymentsAvailable = _subscription?['available'] == true;
    final paymentLinkReady = _subscription?['payment_link_available'] == true ||
        _subscription?['static_payment_link_available'] == true;
"@)
$sub = $sub -replace "Premium scanner access", "Premium access"
$sub = $sub -replace "Paid plans and Premium scanner access will be available", "Paid plans will be available"
Write-Utf8 $subFile $sub

# ---------------------------------------------------------------------------
# 8) REMOVE SCANNER TESTS THAT TARGET DELETED ENDPOINTS.
# ---------------------------------------------------------------------------
$testFile = Join-Path $tests 'test_payments_active.py'
if (Test-Path $testFile) {
    $testsText = Read-Utf8 $testFile
    $testsText = [regex]::Replace($testsText, '(?ms)^\s*def test_scanner_access_is_locked_until_premium_is_paid\(self\):.*?(?=^\s*def )', '')
    $testsText = [regex]::Replace($testsText, '(?ms)^\s*def test_scanner_upload_is_forbidden_without_paid_premium\(self\):.*?(?=^\s*def )', '')
    Write-Utf8 $testFile $testsText
}

# ---------------------------------------------------------------------------
# 9) DOCS / VERSION / FEATURE STATUS
# ---------------------------------------------------------------------------
$readme = Join-Path $root 'README.md'
if (Test-Path $readme) {
    $r = Read-Utf8 $readme
    $r = [regex]::Replace($r, '(?ms)^- Android image capture/gallery scan.*?(?=^\s*- )', '')
    $r = $r -replace 'Premium scanner access', 'Premium access'
    $r = $r -replace 'scanner access', 'Premium access'
    Write-Utf8 $readme $r
}

# ---------------------------------------------------------------------------
# 10) REGENERATE FLUTTER GENERATED FILES / LOCKFILE.
# ---------------------------------------------------------------------------
Push-Location $flutter
try {
    if (Get-Command flutter -ErrorAction SilentlyContinue) {
        flutter pub get
    } else {
        Write-Warning 'Flutter command not found. Run: flutter pub get'
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 11) STATIC CHECKS: no scanner source references should remain.
# ---------------------------------------------------------------------------
$scanRefs = Get-ChildItem $root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(\.venv|build|\.dart_tool|pubspec\.lock|\.git)\\' } |
    Select-String -Pattern 'ScannerScreen|scanner_screen|/v1/scanner|google_mlkit_text_recognition|image_picker|save_image' -SimpleMatch -ErrorAction SilentlyContinue
if ($scanRefs) {
    Write-Warning 'Scanner references still exist in source/docs:'
    $scanRefs | ForEach-Object { Write-Host $_.Path ':' $_.LineNumber $_.Line }
} else {
    Write-Host 'OK: scanner source references removed.' -ForegroundColor Green
}

Write-Host ''
Write-Host '============================================='
Write-Host 'BISNU-X COMPLETE UPDATE FINISHED' -ForegroundColor Cyan
Write-Host '============================================='
Write-Host "Project: $root"
Write-Host "Backup:  $backup"
Write-Host "Premium: ₹399 / 30 days"
Write-Host "Payment link configured: $RazorpayPaymentLink"
Write-Host ''
Write-Host 'IMPORTANT:' -ForegroundColor Yellow
Write-Host '1. Do NOT put RAZORPAY_KEY_SECRET in Flutter/mobile code.'
Write-Host '2. A static Dashboard Payment Link cannot safely identify the logged-in user by itself.'
Write-Host '3. For automatic entitlement, keep the server-created per-user Payment Link + signed payment_link.paid webhook flow enabled.'
Write-Host '4. If you use the static link only for checkout/testing, verify the payment on the server before granting Premium.'
Write-Host ''
Write-Host 'Next test commands:' -ForegroundColor Green
Write-Host '  python -m unittest tests.test_payments_active -v'
Write-Host '  python -m compileall bisnu_x'
Write-Host '  cd flutter; flutter analyze'
Write-Host '  cd flutter; flutter build apk --release'

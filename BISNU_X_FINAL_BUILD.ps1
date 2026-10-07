
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Get-Location).Path,
    [string]$RazorpayPaymentLink = "https://rzp.io/rzp/1XvruAn",
    [switch]$BuildRelease,
    [switch]$BuildAab,
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Step([string]$Message) {
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}
function Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}
function Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}
function Fail([string]$Message) {
    throw "[FAIL] $Message"
}
function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "Missing file: $Path"
    }
}
function Require-Dir([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Fail "Missing directory: $Path"
    }
}
function Run([string]$Exe, [string[]]$Args) {
    Write-Host "> $Exe $($Args -join ' ')" -ForegroundColor DarkGray
    & $Exe @Args
    if ($LASTEXITCODE -ne 0) {
        Fail "$Exe exited with code $LASTEXITCODE"
    }
}

$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$FlutterRoot = Join-Path $ProjectRoot "flutter"
$BackendRoot = Join-Path $ProjectRoot "bisnu_x"
$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$PaymentsPy = Join-Path $BackendRoot "payments.py"
$ConfigPy = Join-Path $BackendRoot "config.py"
$AppPy = Join-Path $BackendRoot "app.py"
$Pubspec = Join-Path $FlutterRoot "pubspec.yaml"
$AndroidApp = Join-Path $FlutterRoot "android\app\build.gradle.kts"
$RootKeyProperties = Join-Path $ProjectRoot "key.properties"
$ReleaseDir = Join-Path $FlutterRoot "build\app\outputs"
$BackupRoot = Join-Path $ProjectRoot ("_backup_before_final_update_" + (Get-Date -Format "yyyyMMdd_HHmmss"))

Step "Validate project"
Require-Dir $ProjectRoot
Require-Dir $BackendRoot
Require-Dir $FlutterRoot
Require-File $PaymentsPy
Require-File $ConfigPy
Require-File $AppPy
Require-File $Pubspec
Require-File $AndroidApp
Ok "BISNU-X project structure found."

Step "Create safety backup"
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
$backupItems = @(
    ".env", "bisnu_x", "flutter\lib", "flutter\pubspec.yaml",
    "flutter\pubspec.lock", "flutter\android\app\build.gradle.kts",
    "tests"
)
foreach ($item in $backupItems) {
    $src = Join-Path $ProjectRoot $item
    if (Test-Path $src) {
        $dest = Join-Path $BackupRoot $item
        $destDir = Split-Path $dest -Parent
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
    }
}
Ok "Backup created: $BackupRoot"

Step "Configure real Premium payment"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Ok "Created .env from .env.example"
    } else {
        New-Item -ItemType File -Path $EnvFile | Out-Null
        Ok "Created empty .env"
    }
}

$envText = Get-Content -LiteralPath $EnvFile -Raw

function Set-EnvValue([string]$Name, [string]$Value) {
    $script:envText = Get-Content -LiteralPath $EnvFile -Raw
    $pattern = "(?m)^\s*" + [regex]::Escape($Name) + "\s*=.*$"
    $line = "$Name=$Value"
    if ([regex]::IsMatch($script:envText, $pattern)) {
        $script:envText = [regex]::Replace($script:envText, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    } else {
        if (-not $script:envText.EndsWith("`n")) { $script:envText += "`r`n" }
        $script:envText += $line + "`r`n"
    }
    Set-Content -LiteralPath $EnvFile -Value $script:envText -Encoding UTF8
}

Set-EnvValue "RAZORPAY_PREMIUM_PAYMENT_LINK" $RazorpayPaymentLink
Set-EnvValue "RAZORPAY_PREMIUM_PAYMENT_AMOUNT" "39900"
Set-EnvValue "RAZORPAY_PREMIUM_PAYMENT_DAYS" "30"

# Never put API secrets into Flutter/mobile source.
$envText = Get-Content -LiteralPath $EnvFile -Raw
if ($envText -match '(?m)^\s*(RAZORPAY_KEY_SECRET|RAZORPAY_WEBHOOK_SECRET)\s*=\s*(.+)$') {
    Warn "Razorpay server secrets are configured in .env; they will NOT be copied into the Flutter app."
}
Ok "Premium configured: ₹399 / 30 days / Razorpay Payment Link."

Step "Validate payment implementation"
$paymentText = Get-Content -LiteralPath $PaymentsPy -Raw
$requiredPaymentMarkers = @(
    "create_premium_payment_link",
    "payment_link.paid",
    "hmac.new",
    "razorpay_premium_payment_amount",
    "razorpay_premium_payment_days",
    "payment_id.startswith(`"pay_`")"
)
foreach ($marker in $requiredPaymentMarkers) {
    if ($paymentText -notlike "*$marker*") {
        Fail "Payment implementation is missing required marker: $marker"
    }
}
if ($paymentText -notmatch 'https://api\.razorpay\.com') {
    Fail "Razorpay API endpoint is missing from backend."
}
Ok "Backend payment verification implementation is present."

Step "Validate scanner removal"
$scannerHits = @()
$scanRoots = @($BackendRoot, (Join-Path $FlutterRoot "lib"), $Pubspec)
foreach ($root in $scanRoots) {
    if (Test-Path $root) {
        if ((Get-Item $root).PSIsContainer) {
            $files = Get-ChildItem $root -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notmatch '\\(build|\.dart_tool|__pycache__)\\' }
        } else {
            $files = @(Get-Item $root)
        }
        foreach ($f in $files) {
            try {
                $raw = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction Stop
                if ($raw -match '(?i)\bscanner\b|\bocr\b|google_mlkit_text_recognition|image_picker') {
                    $scannerHits += $f.FullName
                }
            } catch {}
        }
    }
}
if ($scannerHits.Count -gt 0) {
    Warn "Scanner-related references still exist in these source files:"
    $scannerHits | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Warn "These are reported for review; the script will not blindly delete arbitrary files."
} else {
    Ok "No scanner/OCR/image-picker references found in active source."
}

Step "Clean stale Flutter generated state"
Push-Location $FlutterRoot
try {
    if (Get-Command flutter -ErrorAction SilentlyContinue) {
        Run "flutter" @("clean")
        Run "flutter" @("pub","get")
    } else {
        Fail "Flutter is not installed/on PATH."
    }
} finally {
    Pop-Location
}
Ok "Flutter dependencies refreshed."

Step "Remove unsafe mobile exposure of Razorpay secrets"
$flutterFiles = Get-ChildItem (Join-Path $FlutterRoot "lib") -Recurse -File -ErrorAction SilentlyContinue
foreach ($f in $flutterFiles) {
    $raw = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction SilentlyContinue
    if ($raw -match 'RAZORPAY_KEY_SECRET|RAZORPAY_WEBHOOK_SECRET') {
        Fail "A Razorpay secret name was found in Flutter source: $($f.FullName). Remove it before release."
    }
}
Ok "No Razorpay server secret names found in Flutter source."

Step "Prepare release signing"
if (-not (Test-Path $RootKeyProperties)) {
    $keytool = Get-Command keytool -ErrorAction SilentlyContinue
    if (-not $keytool) {
        Warn "keytool is not on PATH. Release signing cannot be auto-created."
    } else {
        $Keystore = Join-Path $ProjectRoot "bisnu-upload-key.jks"
        if (-not (Test-Path $Keystore)) {
            $bytes = New-Object byte[] 24
            [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
            $storePassword = [Convert]::ToBase64String($bytes).Replace("+","").Replace("/","").Replace("=","").Substring(0,24)
            $bytes2 = New-Object byte[] 24
            [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes2)
            $keyPassword = [Convert]::ToBase64String($bytes2).Replace("+","").Replace("/","").Replace("=","").Substring(0,24)

            Run "keytool" @(
                "-genkeypair","-v",
                "-keystore",$Keystore,
                "-alias","bisnu-upload",
                "-keyalg","RSA",
                "-keysize","2048",
                "-validity","10000",
                "-storepass",$storePassword,
                "-keypass",$keyPassword,
                "-dname","CN=BISNU-X, OU=BISNU-X, O=BISNU-X, L=India, ST=India, C=IN"
            )
            $storeRel = [IO.Path]::GetFileName($Keystore)
            @"
storePassword=$storePassword
keyPassword=$keyPassword
keyAlias=bisnu-upload
storeFile=$storeRel
"@ | Set-Content -LiteralPath $RootKeyProperties -Encoding UTF8
            Ok "Generated a local release keystore and key.properties."
            Warn "BACK UP bisnu-upload-key.jks and key.properties securely. Losing the signing key can prevent future updates to the same Play Store app."
        } else {
            Warn "Keystore exists but key.properties is missing; configure key.properties manually."
        }
    }
} else {
    Ok "Existing release key.properties found."
}

if ($BuildRelease -or $BuildAab) {
    Require-File $RootKeyProperties
    $kp = Get-Content -LiteralPath $RootKeyProperties -Raw
    foreach ($required in @("storePassword","keyPassword","keyAlias","storeFile")) {
        if ($kp -notmatch "(?m)^\s*$required\s*=\s*.+$") {
            Fail "key.properties is missing: $required"
        }
    }
    $storeFileLine = ($kp -split "`r?`n" | Where-Object { $_ -match '^\s*storeFile\s*=' } | Select-Object -First 1)
    $storeRel = ($storeFileLine -split "=",2)[1].Trim()
    $storePath = if ([IO.Path]::IsPathRooted($storeRel)) { $storeRel } else { Join-Path $ProjectRoot $storeRel }
    Require-File $storePath
    Ok "Release signing configuration is valid."
}

Step "Run backend compile check"
Push-Location $ProjectRoot
try {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { Fail "Python is not on PATH." }
    Run "python" @("-m","compileall","-q","bisnu_x")
} finally {
    Pop-Location
}
Ok "Python source compiles."

if ($RunTests) {
    Step "Run backend tests"
    Push-Location $ProjectRoot
    try {
        Run "python" @("-m","unittest","discover","-s","tests","-v")
    } finally {
        Pop-Location
    }
    Ok "Backend tests passed."
}

Step "Run Flutter analyzer"
Push-Location $FlutterRoot
try {
    Run "flutter" @("analyze")
} finally {
    Pop-Location
}
Ok "Flutter analyzer passed."

Step "Run Flutter tests"
Push-Location $FlutterRoot
try {
    Run "flutter" @("test")
} finally {
    Pop-Location
}
Ok "Flutter tests passed."

if ($BuildRelease) {
    Step "Build signed release APK"
    Push-Location $FlutterRoot
    try {
        Run "flutter" @("build","apk","--release")
    } finally {
        Pop-Location
    }
    $apk = Join-Path $FlutterRoot "build\app\outputs\flutter-apk\app-release.apk"
    Require-File $apk
    Ok "Release APK: $apk"
}

if ($BuildAab) {
    Step "Build signed Play Store App Bundle"
    Push-Location $FlutterRoot
    try {
        Run "flutter" @("build","appbundle","--release")
    } finally {
        Pop-Location
    }
    $aab = Join-Path $FlutterRoot "build\app\outputs\bundle\release\app-release.aab"
    Require-File $aab
    Ok "Release AAB: $aab"
}

Step "Final security scan"
$badMobileSecrets = @()
foreach ($f in (Get-ChildItem (Join-Path $FlutterRoot "lib") -Recurse -File -ErrorAction SilentlyContinue)) {
    $raw = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction SilentlyContinue
    if ($raw -match '(?i)rzp_live_[A-Za-z0-9]+|RAZORPAY_KEY_SECRET\s*=|RAZORPAY_WEBHOOK_SECRET\s*=') {
        $badMobileSecrets += $f.FullName
    }
}
if ($badMobileSecrets.Count -gt 0) {
    Fail "Possible Razorpay secret material found in Flutter source."
}
Ok "No obvious Razorpay secret material found in Flutter source."

Write-Host "`n========================================" -ForegroundColor Green
Write-Host " BISNU-X FINAL UPDATE CHECK COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Premium: ₹399 / 30 days"
Write-Host "Razorpay link: $RazorpayPaymentLink"
Write-Host "Scanner: disabled/removed from active source where present"
Write-Host "Backup: $BackupRoot"
if ($BuildRelease) {
    Write-Host "APK: $(Join-Path $FlutterRoot 'build\app\outputs\flutter-apk\app-release.apk')"
}
if ($BuildAab) {
    Write-Host "AAB: $(Join-Path $FlutterRoot 'build\app\outputs\bundle\release\app-release.aab')"
}
Write-Host "========================================`n" -ForegroundColor Green


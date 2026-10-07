param(
    [Parameter(Mandatory = $true)]
    [string]$ApiUrl,
    [Parameter(Mandatory = $true)]
    [switch]$ConfirmSigningKeyIsRotated,
    [string]$FlutterExecutable = "C:\src\flutter\bin\flutter.bat"
)

$ErrorActionPreference = "Stop"

$parsedApiUrl = $null
if (-not [Uri]::TryCreate($ApiUrl, [UriKind]::Absolute, [ref]$parsedApiUrl) -or
    $parsedApiUrl.Scheme -ne "https") {
    throw "ApiUrl must be an absolute HTTPS URL."
}
if (-not $ConfirmSigningKeyIsRotated) {
    throw "The prior upload keystore is compromised. Rotate it and pass -ConfirmSigningKeyIsRotated only after updating key.properties and registering the new certificate."
}
if (-not (Test-Path -LiteralPath $FlutterExecutable -PathType Leaf)) {
    throw "Flutter executable was not found: $FlutterExecutable"
}

$projectDirectory = $PSScriptRoot
$configuredSigningProperties = $env:BISNU_SIGNING_PROPERTIES
$signingProperties = if ([string]::IsNullOrWhiteSpace($configuredSigningProperties)) {
    Join-Path $projectDirectory "..\key.properties"
} else {
    $configuredSigningProperties
}
if (-not (Test-Path -LiteralPath $signingProperties -PathType Leaf)) {
    throw "Release signing properties are missing: $signingProperties"
}
$storeFileLine = Select-String -LiteralPath $signingProperties `
    -Pattern '^\s*storeFile\s*=' | Select-Object -First 1
if (-not $storeFileLine) {
    throw "Release signing properties do not configure a keystore path."
}
$configuredStore = ($storeFileLine.Line -split '=', 2)[1].Trim()
$keystore = if ([IO.Path]::IsPathRooted($configuredStore)) {
    $configuredStore
} else {
    Join-Path $projectDirectory "..\..\$configuredStore"
}
if (-not (Test-Path -LiteralPath $keystore -PathType Leaf)) {
    throw "Release keystore configured by key.properties was not found."
}

Push-Location $projectDirectory
try {
    & $FlutterExecutable build apk --release --target-platform android-arm64 `
        "--dart-define=BISNU_API_URL=$($ApiUrl.TrimEnd('/'))"
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter release build failed (exit $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}

$apkPath = Join-Path $projectDirectory "build\app\outputs\flutter-apk\app-release.apk"
if (-not (Test-Path -LiteralPath $apkPath -PathType Leaf)) {
    throw "Flutter returned success, but the release APK was not found at $apkPath."
}

$buildToolsDirectory = Join-Path $env:LOCALAPPDATA "Android\Sdk\build-tools"
$apksigner = Get-ChildItem -Path $buildToolsDirectory -Filter apksigner.bat `
    -Recurse -ErrorAction SilentlyContinue |
    Sort-Object { [version]($_.Directory.Name -replace '-.*$', '') } -Descending |
    Select-Object -First 1
if (-not $apksigner) {
    throw "Android SDK apksigner was not found. APK built at $apkPath, but signature verification is required before distribution."
}

& $apksigner.FullName verify --verbose $apkPath
if ($LASTEXITCODE -ne 0) {
    throw "APK signature verification failed."
}

$aapt = Join-Path $apksigner.DirectoryName "aapt.exe"
if (-not (Test-Path -LiteralPath $aapt -PathType Leaf)) {
    throw "Android SDK aapt was not found beside apksigner; APK package verification is required."
}
$badging = & $aapt dump badging $apkPath
if ($LASTEXITCODE -ne 0) {
    throw "Could not read APK package metadata."
}
if (-not ($badging | Select-String -Pattern "^package: name='app\.bisnux\.mobile'")) {
    throw "Built APK application ID is not app.bisnux.mobile."
}

$apk = Get-Item -LiteralPath $apkPath
$hash = (Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash
Write-Host "Signed ARM64 APK: $($apk.FullName)"
Write-Host "Application ID: app.bisnux.mobile"
Write-Host "Size: $($apk.Length) bytes"
Write-Host "SHA-256: $hash"
Write-Warning "Verify live /health and /api/status, real model chat/search, account registration/login, and history restoration on a physical Android device before publishing."

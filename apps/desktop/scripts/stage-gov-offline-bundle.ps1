<#
.SYNOPSIS
  Stages the complete TchueKAM Desktop Air-Gapped / Government IT Offline Deployment Bundle.

.DESCRIPTION
  Assembles:
    - installers/ : TchueKAM-Setup.exe, Tchuekam-Setup-win-x64.msi, TchueKAM-Setup.exe.blockmap, latest.yml,
                    and Tchuekam-Enterprise-CodeSigning.cer (if present)
    - offline-models/business-agent/runtime/ : llama-server.exe and CPU inference DLLs
    - offline-models/business-agent/models/  : Qwen3-0.6B-Q4_K_M.gguf, SmolLM2-360M-Instruct-Q4_K_M.gguf, config.json
    - offline-models/models/kokoro/          : kokoro-v1.0.int8.onnx, voices-v1.0.bin
    - offline-models/bin/                    : uv.exe, uvw.exe, uvx.exe
    - Install-TchuekamOffline.ps1            : Turnkey offline installer + integrity verifier for IT admins
    - SHA256SUMS.txt & bundle-manifest.json  : Complete cryptographic inventory
#>
param(
  [string]$ReleaseDir = (Join-Path $PSScriptRoot "..\release"),
  [string]$SourceHermesHome = (Join-Path $env:LOCALAPPDATA "hermes"),
  [string]$OutputDir = (Join-Path $PSScriptRoot "..\release\gov-offline-bundle")
)

$ErrorActionPreference = "Stop"
$resolvedRelease = [System.IO.Path]::GetFullPath($ReleaseDir)
$resolvedSource = [System.IO.Path]::GetFullPath($SourceHermesHome)
$resolvedOut = [System.IO.Path]::GetFullPath($OutputDir)

if (Test-Path $resolvedOut) {
  Remove-Item -Recurse -Force $resolvedOut
}

$installersDir = Join-Path $resolvedOut "installers"
$modelsRoot = Join-Path $resolvedOut "offline-models"
New-Item -ItemType Directory -Path $installersDir -Force | Out-Null
New-Item -ItemType Directory -Path $modelsRoot -Force | Out-Null

# 1. Copy verified Windows installers and certificate
$installerFiles = @(
  "TchueKAM-Setup.exe",
  "Tchuekam-Setup-win-x64.msi",
  "TchueKAM-Setup.exe.blockmap",
  "latest.yml",
  "Tchuekam-Enterprise-CodeSigning.cer"
)
foreach ($name in $installerFiles) {
  $src = Join-Path $resolvedRelease $name
  if (Test-Path $src) {
    Copy-Item $src (Join-Path $installersDir $name) -Force
  } elseif ($name -ne "Tchuekam-Enterprise-CodeSigning.cer") {
    throw "Required release artifact missing: $src"
  }
}

# 2. Copy offline Business Local AI runtime & GGUF models
$bizSrc = Join-Path $resolvedSource "business-agent"
if (Test-Path $bizSrc) {
  $bizDest = Join-Path $modelsRoot "business-agent"
  New-Item -ItemType Directory -Path $bizDest -Force | Out-Null
  foreach ($sub in @("runtime", "models", "config.json")) {
    $s = Join-Path $bizSrc $sub
    if (Test-Path $s) {
      Copy-Item $s (Join-Path $bizDest $sub) -Recurse -Force
    }
  }
}

# 3. Copy offline Kokoro TTS voice models
$kokoroSrc = Join-Path $resolvedSource "models\kokoro"
if (Test-Path $kokoroSrc) {
  $kokoroDest = Join-Path $modelsRoot "models\kokoro"
  New-Item -ItemType Directory -Path (Split-Path $kokoroDest -Parent) -Force | Out-Null
  Copy-Item $kokoroSrc $kokoroDest -Recurse -Force
}

# 4. Copy offline uv binaries
$binSrc = Join-Path $resolvedSource "bin"
if (Test-Path $binSrc) {
  $binDest = Join-Path $modelsRoot "bin"
  Copy-Item $binSrc $binDest -Recurse -Force
}

# 5. Write turnkey air-gapped IT deployment script
$deployScript = @'
<#
.SYNOPSIS
  Air-Gapped / Government IT Offline Installer for TchueKAM Desktop v0.15.3.

.PARAMETER HermesHome
  Target HERMES_HOME directory for offline models and runtime (defaults to %LOCALAPPDATA%\hermes).

.PARAMETER InstallDir
  Optional target installation directory for the NSIS installer (/D=<InstallDir>).

.PARAMETER UseMsi
  Use the Windows MSI package (msiexec /i ... /qn /norestart) instead of the NSIS .exe installer.

.PARAMETER TrustCertificate
  Imports Tchuekam-Enterprise-CodeSigning.cer into CurrentUser Trusted Root & Trusted Publishers.

.PARAMETER SkipInstallerExecution
  Only verify SHA-256 checksums and pre-seed offline models without running the setup binary.
#>
param(
  [string]$HermesHome = (Join-Path $env:LOCALAPPDATA "hermes"),
  [string]$InstallDir = "",
  [switch]$UseMsi,
  [switch]$TrustCertificate,
  [switch]$SkipInstallerExecution
)

$ErrorActionPreference = "Stop"
$bundleRoot = $PSScriptRoot
$sumsFile = Join-Path $bundleRoot "SHA256SUMS.txt"

if (-not (Test-Path $sumsFile)) {
  throw "Missing SHA256SUMS.txt in $bundleRoot"
}

Write-Host "[1/4] Verifying SHA-256 cryptographic checksums..."
$lines = Get-Content $sumsFile | Where-Object { $_.Trim() -ne "" }
foreach ($line in $lines) {
  $parts = $line -split "\s{2,}", 2
  if ($parts.Count -ne 2) { continue }
  $expected = $parts[0].Trim().ToUpperInvariant()
  $relPath = $parts[1].Trim()
  $fullPath = Join-Path $bundleRoot $relPath
  if (-not (Test-Path $fullPath)) {
    throw "Missing file listed in SHA256SUMS.txt: $relPath"
  }
  $actual = (Get-FileHash $fullPath -Algorithm SHA256).Hash.ToUpperInvariant()
  if ($actual -ne $expected) {
    throw "SHA-256 mismatch for $relPath (expected $expected, got $actual)"
  }
}
Write-Host "      All $($lines.Count) bundle files passed SHA-256 verification."

$cerPath = Join-Path $bundleRoot "installers\Tchuekam-Enterprise-CodeSigning.cer"
if ($TrustCertificate -and (Test-Path $cerPath)) {
  Write-Host "[2/4] Importing Enterprise Code Signing certificate..."
  Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
  Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\TrustedPublisher" | Out-Null
} else {
  Write-Host "[2/4] Skipping certificate store import (pass -TrustCertificate to import)."
}

Write-Host "[3/4] Seeding offline AI runtime and models into $HermesHome ..."
New-Item -ItemType Directory -Path $HermesHome -Force | Out-Null
$offlineModels = Join-Path $bundleRoot "offline-models"
if (Test-Path $offlineModels) {
  Get-ChildItem $offlineModels | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $HermesHome $_.Name) -Recurse -Force
  }
}
Write-Host "      Offline models seeded (Business Local AI GGUF + llama-server + Kokoro TTS)."

if ($SkipInstallerExecution) {
  Write-Host "[4/4] SkipInstallerExecution set — offline model seeding complete."
  exit 0
}

if ($UseMsi) {
  $msi = Join-Path $bundleRoot "installers\Tchuekam-Setup-win-x64.msi"
  Write-Host "[4/4] Running silent MSI installation ($msi)..."
  $p = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i","`"$msi`"","/qn","/norestart" -Wait -PassThru
  if ($p.ExitCode -ne 0) {
    throw "MSI installation exited with code $($p.ExitCode)"
  }
} else {
  $exe = Join-Path $bundleRoot "installers\TchueKAM-Setup.exe"
  $argList = @("/S")
  if ($InstallDir) {
    $resolvedInstall = [System.IO.Path]::GetFullPath($InstallDir)
    # NSIS requires /D=... as the final argument without quotes
    $argList += "/D=$resolvedInstall"
  }
  Write-Host "[4/4] Running silent NSIS installation ($exe $($argList -join ' '))..."
  $p = Start-Process -FilePath $exe -ArgumentList $argList -Wait -PassThru
  if ($p.ExitCode -ne 0) {
    throw "NSIS installation exited with code $($p.ExitCode)"
  }
}
Write-Host "TchueKAM Desktop v0.15.3 offline installation completed successfully."
'@

$deployScriptPath = Join-Path $resolvedOut "Install-TchuekamOffline.ps1"
[System.IO.File]::WriteAllText($deployScriptPath, $deployScript, (New-Object System.Text.UTF8Encoding($false)))

# 6. Compute SHA256SUMS.txt and bundle-manifest.json
$allFiles = Get-ChildItem $resolvedOut -Recurse -File |
  Where-Object { $_.Name -notin @("SHA256SUMS.txt", "bundle-manifest.json") } |
  Sort-Object FullName

$sumLines = New-Object System.Collections.Generic.List[string]
$manifestEntries = New-Object System.Collections.Generic.List[object]
$totalBytes = 0L

foreach ($f in $allFiles) {
  $rel = $f.FullName.Substring($resolvedOut.Length).TrimStart('\', '/')
  $hash = (Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  $sumLines.Add("$hash  $rel")
  $totalBytes += $f.Length
  $manifestEntries.Add([ordered]@{
    path   = ($rel -replace '\\', '/')
    size   = $f.Length
    sha256 = $hash
  })
}

$sumsOut = Join-Path $resolvedOut "SHA256SUMS.txt"
[System.IO.File]::WriteAllLines($sumsOut, $sumLines, (New-Object System.Text.UTF8Encoding($false)))

$manifestObj = [ordered]@{
  product     = "TchueKAM Desktop"
  version     = "0.15.3"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  fileCount   = $manifestEntries.Count
  totalBytes  = $totalBytes
  files       = $manifestEntries
}
$manifestJson = $manifestObj | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText((Join-Path $resolvedOut "bundle-manifest.json"), $manifestJson, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "[stage-gov-bundle] Staged $($manifestEntries.Count) files ($([math]::Round($totalBytes / 1MB, 2)) MB) -> $resolvedOut"

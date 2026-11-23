<#
.SYNOPSIS
  Signs TchueKAM Desktop Windows release binaries (.exe and .msi) with Authenticode SHA-256
  and updates latest.yml (sha512 + size) to match the signed NSIS installer.

.DESCRIPTION
  Supports three certificate sources:
    1. -Thumbprint <sha1> : existing CodeSigning certificate in Cert:\CurrentUser\My or Cert:\LocalMachine\My
    2. -PfxPath <path>    : PKCS#12 (.pfx) certificate file (with optional -PfxPassword)
    3. -EnterpriseSelfSign: finds or creates an Enterprise Intranet CodeSigning certificate
                            (CN=TchuekaM Enterprise Code Signing, O=TchuekaM, C=CM) in Cert:\CurrentUser\My
                            and exports the public .cer to release\Tchuekam-Enterprise-CodeSigning.cer
                            for Active Directory GPO / Intune deployment.
#>
param(
  [string]$ReleaseDir = (Join-Path $PSScriptRoot "..\release"),
  [string]$Thumbprint = $env:TCHUEKAM_SIGN_THUMBPRINT,
  [string]$PfxPath = $env:TCHUEKAM_SIGN_PFX_PATH,
  [string]$PfxPassword = $env:TCHUEKAM_SIGN_PFX_PASSWORD,
  [string]$TimestampServer = "",
  [switch]$EnterpriseSelfSign,
  [switch]$InstallToCurrentUserTrust
)

$ErrorActionPreference = "Stop"
$resolvedRelease = [System.IO.Path]::GetFullPath($ReleaseDir)
if (-not (Test-Path $resolvedRelease)) {
  throw "Release directory not found: $resolvedRelease"
}

$cert = $null
if ($Thumbprint) {
  $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
    Where-Object { $_.Thumbprint -eq $Thumbprint } |
    Select-Object -First 1
  if (-not $cert) {
    throw "No certificate found matching thumbprint: $Thumbprint"
  }
} elseif ($PfxPath) {
  if (-not (Test-Path $PfxPath)) {
    throw "PFX file not found: $PfxPath"
  }
  if ($PfxPassword) {
    $sec = ConvertTo-SecureString $PfxPassword -AsPlainText -Force
    $cert = Get-PfxCertificate -FilePath $PfxPath -Password $sec
  } else {
    $cert = Get-PfxCertificate -FilePath $PfxPath
  }
} elseif ($EnterpriseSelfSign) {
  $subject = "CN=TchuekaM Enterprise Code Signing, O=TchuekaM, C=CM"
  $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -eq $subject -and $_.NotAfter -gt (Get-Date).AddDays(30) } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

  if (-not $cert) {
    Write-Host "[sign-windows] Generating Enterprise Code Signing certificate ($subject)..."
    $cert = New-SelfSignedCertificate `
      -Type CodeSigningCert `
      -Subject $subject `
      -FriendlyName "TchuekaM Enterprise Code Signing" `
      -KeyAlgorithm RSA `
      -KeyLength 2048 `
      -HashAlgorithm "SHA256" `
      -CertStoreLocation "Cert:\CurrentUser\My" `
      -NotAfter (Get-Date).AddYears(3)
  }

  $cerOut = Join-Path $resolvedRelease "Tchuekam-Enterprise-CodeSigning.cer"
  Export-Certificate -Cert $cert -FilePath $cerOut -Force | Out-Null
  Write-Host "[sign-windows] Exported public certificate -> $cerOut (Thumbprint: $($cert.Thumbprint))"

  if ($InstallToCurrentUserTrust) {
    Import-Certificate -FilePath $cerOut -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
    Import-Certificate -FilePath $cerOut -CertStoreLocation "Cert:\CurrentUser\TrustedPublisher" | Out-Null
    Write-Host "[sign-windows] Installed certificate into CurrentUser\Root and CurrentUser\TrustedPublisher"
  }
} else {
  throw "Specify -Thumbprint, -PfxPath, or -EnterpriseSelfSign."
}

$targets = @(
  (Join-Path $resolvedRelease "win-unpacked\Tchuekam.exe"),
  (Join-Path $resolvedRelease "TchueKAM-Setup.exe"),
  (Join-Path $resolvedRelease "Tchuekam-Setup-win-x64.msi")
) | Where-Object { Test-Path $_ }

foreach ($target in $targets) {
  Write-Host "[sign-windows] Signing $target ..."
  $signArgs = @{
    FilePath      = $target
    Certificate   = $cert
    HashAlgorithm = "SHA256"
  }
  if ($TimestampServer) {
    $signArgs["TimestampServer"] = $TimestampServer
  }
  $sig = Set-AuthenticodeSignature @signArgs
  if ($sig.Status -eq "NotSigned" -or $sig.Status -eq "HashMismatch") {
    throw "Failed to sign $target : Status=$($sig.Status) $($sig.StatusMessage)"
  }
  Write-Host "[sign-windows] Signed $(Split-Path $target -Leaf) (Status: $($sig.Status), Thumbprint: $($sig.SignerCertificate.Thumbprint))"
}

$setupExe = Join-Path $resolvedRelease "TchueKAM-Setup.exe"
$latestYml = Join-Path $resolvedRelease "latest.yml"
if ((Test-Path $setupExe) -and (Test-Path $latestYml)) {
  $bytes = [System.IO.File]::ReadAllBytes($setupExe)
  $sha512 = [System.Security.Cryptography.SHA512]::Create()
  try {
    $hashBytes = $sha512.ComputeHash($bytes)
  } finally {
    $sha512.Dispose()
  }
  $b64 = [Convert]::ToBase64String($hashBytes)
  $size = $bytes.LongLength

  $yml = Get-Content $latestYml -Raw
  $yml = [regex]::Replace($yml, "sha512:\s*\S+", "sha512: $b64")
  $yml = [regex]::Replace($yml, "size:\s*\d+", "size: $size")
  [System.IO.File]::WriteAllText($latestYml, $yml, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "[sign-windows] Updated latest.yml (size=$size, sha512=$b64)"
}

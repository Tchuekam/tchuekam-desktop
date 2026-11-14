# Tests for how install.ps1's Install-Repository handles a pinned commit/tag.
#
# Run from a PowerShell prompt:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test-install-ps1-repository-pin.ps1
#
# The desktop app stamps each build with the commit and branch it was built
# from, and its first launch asks install.ps1 to clone exactly that.  A branch
# that was never pushed (or was deleted after the PR merged) used to fail the
# whole install, so the app could never finish its first-launch setup.
#
# These tests run the real Install-Repository / Set-RepositoryPin functions
# (lifted out of install.ps1 with the PowerShell parser) against a throwaway
# local "origin", so they need git but no network: the GitHub archive download
# of the ZIP fallback is replaced by a test double.  Pass -InstallScript to run
# them against another copy of the script, e.g. an older revision (one without
# the fixes will fall into its real ZIP fallback and try github.com).  Takes
# about two minutes.

param(
    [string]$InstallScript
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
if (-not $InstallScript) { $InstallScript = Join-Path $repoRoot "scripts\install.ps1" }
if (-not (Test-Path $InstallScript)) { throw "Could not locate install.ps1 at $InstallScript" }

# Install-Repository runs `git config --global`, and this test keeps that off the
# real config with GIT_CONFIG_GLOBAL, which git only honours from 2.32 (the
# fixture also needs `git init -b`, from 2.28).  Refuse to run on older git
# rather than write the developer's ~/.gitconfig.
$gitVersion = [version](((& git --version) -replace '^git version (\d+\.\d+(\.\d+)?).*$', '$1'))
if ($gitVersion -lt [version]"2.32") {
    Write-Host "SKIP: needs git >= 2.32 (found $gitVersion)"
    exit 0
}

$failures = 0
function Assert-Equal {
    # $Actual is $null when the install threw before anything was checked out;
    # report that as a failed assertion instead of aborting the whole run.
    param([Parameter(Mandatory=$true)] $Expected,
          [Parameter(Mandatory=$true)] [AllowNull()] [AllowEmptyString()] $Actual,
          [Parameter(Mandatory=$true)] [string]$Label)
    if ($Expected -ne $Actual) {
        Write-Host "FAIL: $Label" -ForegroundColor Red
        Write-Host "  expected: $Expected"
        Write-Host "  actual:   $Actual"
        $script:failures++
    } else {
        Write-Host "OK: $Label" -ForegroundColor Green
    }
}
function Assert-True {
    param([Parameter(Mandatory=$true)] $Condition,
          [Parameter(Mandatory=$true)] [string]$Label)
    if (-not $Condition) {
        Write-Host "FAIL: $Label" -ForegroundColor Red
        $script:failures++
    } else {
        Write-Host "OK: $Label" -ForegroundColor Green
    }
}

# --- Lift the functions under test out of install.ps1 -------------------------
$ast = [System.Management.Automation.Language.Parser]::ParseFile($InstallScript, [ref]$null, [ref]$null)
$wanted = @("Set-RepositoryPin", "Install-Repository")
$found = $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $wanted -contains $node.Name
}, $true)
if (-not ($found | Where-Object { $_.Name -eq "Install-Repository" })) {
    throw "Install-Repository not found in $InstallScript"
}
foreach ($fn in $found) { . ([scriptblock]::Create($fn.Extent.Text)) }

$messages = New-Object System.Collections.Generic.List[string]
function Write-Info    { param([string]$Message) $script:messages.Add("INFO: $Message") }
function Write-Success { param([string]$Message) $script:messages.Add("OK: $Message") }
function Write-Warn    { param([string]$Message) $script:messages.Add("WARN: $Message") }
function Write-Err     { param([string]$Message) $script:messages.Add("ERR: $Message") }

# --- Throwaway origin ---------------------------------------------------------
# main:  A
# topic: A -> B       (pushed; also tagged v1)
# C:     a local-only commit that origin has never seen
$root = Join-Path ([System.IO.Path]::GetTempPath()) ("install-pin-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $root | Out-Null
$origin = Join-Path $root "origin.git"
$seed = Join-Path $root "seed"

# Install-Repository runs `git config --global`; keep that off the real config.
$savedEnv = @{}
foreach ($name in "GIT_CONFIG_GLOBAL", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "GIT_TERMINAL_PROMPT") {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name)
}
$env:GIT_CONFIG_GLOBAL = Join-Path $root "gitconfig"
$env:GIT_TERMINAL_PROMPT = "0"

# Fixture-building git calls.  Under $ErrorActionPreference = "Stop", Windows
# PowerShell 5.1 turns any stderr line from a native command (git's "Cloning
# into ..." progress) into a terminating error once stderr is redirected, so
# these run under "Continue" and are judged by exit code instead.  Returns
# stdout only.
function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments=$true)] $GitArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & git -c user.name=test -c user.email=test@example.invalid @GitArgs 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "git $($GitArgs -join ' ') failed: $out" }
    (@($out) | Where-Object { $_ -is [string] }) -join "`n"
}

try {
    Invoke-Git init --bare -b main $origin | Out-Null
    Invoke-Git clone $origin $seed | Out-Null
    Set-Content -Path (Join-Path $seed "f.txt") -Value "a"
    Invoke-Git -C $seed add f.txt | Out-Null
    Invoke-Git -C $seed commit -m "A" | Out-Null
    Invoke-Git -C $seed branch -M main | Out-Null
    Invoke-Git -C $seed push origin main | Out-Null
    $commitA = (Invoke-Git -C $seed rev-parse HEAD).Trim()

    Invoke-Git -C $seed checkout -b topic | Out-Null
    Set-Content -Path (Join-Path $seed "f.txt") -Value "b"
    Invoke-Git -C $seed commit -am "B" | Out-Null
    Invoke-Git -C $seed push origin topic | Out-Null
    $commitB = (Invoke-Git -C $seed rev-parse HEAD).Trim()
    Invoke-Git -C $seed tag v1 | Out-Null
    Invoke-Git -C $seed push origin v1 | Out-Null

    Set-Content -Path (Join-Path $seed "f.txt") -Value "c"
    Invoke-Git -C $seed commit -am "C (never pushed)" | Out-Null
    $commitC = (Invoke-Git -C $seed rev-parse HEAD).Trim()

    function Invoke-Scenario {
        # Runs Install-Repository with the given pin against the fixture and
        # returns what ended up checked out (or the error it threw).
        param([string]$Branch, [string]$Commit = "", [string]$Tag = "", [string]$Dir)
        $script:Branch = $Branch
        $script:Commit = $Commit
        $script:Tag = $Tag
        $script:InstallDir = $Dir
        $script:RepoUrlSsh = Join-Path $root "no-such-remote.git"
        $script:RepoUrlHttps = $origin
        $script:messages.Clear()
        $result = @{ Error = $null; Head = $null; Ref = $null }
        try {
            Install-Repository
            # An archive install has no commits, so these may legitimately fail.
            $result.Head = Get-GitValue $Dir rev-parse HEAD
            $result.Ref = Get-GitValue $Dir rev-parse --abbrev-ref HEAD
        } catch {
            $result.Error = "$_"
        }
        $result
    }

    function Get-FileText {
        # The text of a file, or $null when the install under test never made it.
        param([string]$Path)
        if (Test-Path -LiteralPath $Path) { (Get-Content -LiteralPath $Path) -join "" } else { $null }
    }

    function Get-GitValue {
        # stdout of one git command in $Dir, or $null when it fails.
        param([string]$Dir, [Parameter(ValueFromRemainingArguments=$true)] $GitArgs)
        $previous = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $out = & git -C $Dir @GitArgs 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { ([string]$out).Trim() } else { $null }
        } finally {
            $ErrorActionPreference = $previous
        }
    }

    # -------------------------------------------------------------------------
    Write-Host ""
    Write-Host "-- commit pinned, branch no longer on the remote --"
    $r = Invoke-Scenario -Branch "gone-topic" -Commit $commitB -Dir (Join-Path $root "t1")
    Assert-True ($null -eq $r.Error) -Label "install succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitB -Actual $r.Head -Label "checkout lands on the pinned commit"

    Write-Host ""
    Write-Host "-- commit pinned but never pushed, branch exists --"
    $r = Invoke-Scenario -Branch "topic" -Commit $commitC -Dir (Join-Path $root "t2")
    Assert-True ($null -eq $r.Error) -Label "install succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitB -Actual $r.Head -Label "falls back to the branch tip"
    Assert-True (($messages | Where-Object { $_ -like "WARN:*$commitC*" }).Count -ge 1) -Label "warns that the pinned commit is unavailable"

    Write-Host ""
    Write-Host "-- commit pinned but never pushed, branch gone too --"
    $r = Invoke-Scenario -Branch "gone-topic" -Commit $commitC -Dir (Join-Path $root "t3")
    Assert-True ($null -eq $r.Error) -Label "install succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitA -Actual $r.Head -Label "stays on the remote's default branch"

    Write-Host ""
    Write-Host "-- no pin: branch clone still honours -Branch --"
    $r = Invoke-Scenario -Branch "topic" -Dir (Join-Path $root "t4")
    Assert-True ($null -eq $r.Error) -Label "install succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitB -Actual $r.Head -Label "checks out the requested branch"
    Assert-Equal -Expected "topic" -Actual $r.Ref -Label "on that branch, not detached"

    Write-Host ""
    Write-Host "-- tag pinned --"
    $r = Invoke-Scenario -Branch "gone-topic" -Tag "v1" -Dir (Join-Path $root "t5")
    Assert-True ($null -eq $r.Error) -Label "install succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitB -Actual $r.Head -Label "checkout lands on the tagged commit"

    Write-Host ""
    Write-Host "-- tag pinned but missing --"
    $r = Invoke-Scenario -Branch "main" -Tag "nope" -Dir (Join-Path $root "t6")
    Assert-True ($null -eq $r.Error) -Label "install succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitA -Actual $r.Head -Label "falls back to the branch tip"

    Write-Host ""
    Write-Host "-- re-running over an existing install --"
    $dir = Join-Path $root "t7"
    $r = Invoke-Scenario -Branch "main" -Commit $commitA -Dir $dir
    Assert-Equal -Expected $commitA -Actual $r.Head -Label "first run pins A"
    $r = Invoke-Scenario -Branch "main" -Commit $commitB -Dir $dir
    Assert-True ($null -eq $r.Error) -Label "update succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitB -Actual $r.Head -Label "update moves to the new pin"
    $r = Invoke-Scenario -Branch "topic" -Commit $commitC -Dir $dir
    Assert-True ($null -eq $r.Error) -Label "update with an unpushed pin succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitB -Actual $r.Head -Label "update falls back to the branch tip"

    # -------------------------------------------------------------------------
    Write-Host ""
    Write-Host "-- a pin the remote has, but the checkout fails for a real reason --"
    $dir = Join-Path $root "t8"
    $r = Invoke-Scenario -Branch "main" -Commit $commitA -Dir $dir
    Assert-Equal -Expected $commitA -Actual $r.Head -Label "first run pins A"
    Set-Content -Path (Join-Path $dir "f.txt") -Value "local edit"
    $r = Invoke-Scenario -Branch "main" -Commit $commitB -Dir $dir
    Assert-True (($null -ne $r.Error) -and ($r.Error -like "*git checkout*")) -Label "the failed checkout is reported, not papered over (error: $($r.Error))"
    Assert-True (($messages | Where-Object { $_ -like "WARN:*not available from the remote*" }).Count -eq 0) -Label "no false 'not available from the remote' warning"
    Assert-Equal -Expected $commitA -Actual (& git -C $dir rev-parse HEAD).Trim() -Label "the checkout is left where it was"

    Write-Host ""
    Write-Host "-- re-running over an install whose local branch is behind the remote --"
    $dir = Join-Path $root "t9"
    $r = Invoke-Scenario -Branch "main" -Dir $dir
    Assert-Equal -Expected $commitA -Actual $r.Head -Label "first run installs main at A"
    Invoke-Git -C $seed checkout main | Out-Null
    Set-Content -Path (Join-Path $seed "f.txt") -Value "d"
    Invoke-Git -C $seed commit -am "D" | Out-Null
    Invoke-Git -C $seed push origin main | Out-Null
    $commitD = (Invoke-Git -C $seed rev-parse HEAD).Trim()
    $r = Invoke-Scenario -Branch "main" -Commit $commitC -Dir $dir
    Assert-True ($null -eq $r.Error) -Label "update with an unpushed pin succeeds (error: $($r.Error))"
    Assert-Equal -Expected $commitD -Actual $r.Head -Label "falls back to the CURRENT branch tip, not a stale local branch"

    # -------------------------------------------------------------------------
    # ZIP fallback.  It exists for machines where git itself misbehaves, so make
    # `git clone` fail and serve the GitHub archive downloads from local zips.
    $zipDir = Join-Path $root "zips"
    New-Item -ItemType Directory -Path $zipDir | Out-Null
    function New-ArchiveZip {
        # GitHub archives hold a single top-level directory; so does this.
        param([string]$Ref, [string]$Name)
        $path = Join-Path $zipDir "$Name.zip"
        # Long options only: Invoke-Git is an advanced function, so PowerShell
        # would bind a short "-o" to its common parameters.
        Invoke-Git -C $seed archive --format=zip "--prefix=tchuekam-desktop-$Name/" "--output=$path" $Ref | Out-Null
        $path
    }
    $archives = @{}
    function Invoke-WebRequest {
        param([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing)
        $key = $Uri -replace '^.*/archive/', ''
        if (-not $script:archives.ContainsKey($key)) { throw "404 Not Found (test double): $Uri" }
        Copy-Item -LiteralPath $script:archives[$key] -Destination $OutFile
    }
    $failClones = $false
    function git {
        if ($script:failClones -and ($args -contains "clone")) { $global:LASTEXITCODE = 128; return }
        & git.exe @args
    }
    function Get-InstallerTempFiles {
        @(Get-ChildItem $env:TEMP -Filter "hermes-agent-*" -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    }

    Write-Host ""
    Write-Host "-- ZIP fallback, archive of the pinned commit available --"
    $archives["$commitB.zip"] = New-ArchiveZip $commitB "pinned-b"
    $failClones = $true
    $tempBefore = Get-InstallerTempFiles
    $dir = Join-Path $root "t10"
    $r = Invoke-Scenario -Branch "gone-topic" -Commit $commitB -Dir $dir
    Assert-True ($null -eq $r.Error) -Label "install succeeds from the archive (error: $($r.Error))"
    Assert-Equal -Expected "b" -Actual (Get-FileText (Join-Path $dir "f.txt")) -Label "the files come from the pinned commit's archive"
    Assert-True (($messages | Where-Object { $_ -like "WARN:*not available from the remote*" -or $_ -like "WARN:*archive for the pinned ref*" }).Count -eq 0) -Label "no false warnings about the pin"
    Assert-Equal -Expected 0 -Actual (@(Get-InstallerTempFiles | Where-Object { $tempBefore -notcontains $_ })).Count -Label "temp files are cleaned up"

    Write-Host ""
    Write-Host "-- ZIP fallback, archive of the pinned commit missing, branch archive available --"
    # origin's topic is B; the seed's own local topic also carries the unpushed C.
    $archives = @{ "refs/heads/topic.zip" = (New-ArchiveZip $commitB "branch-topic") }
    $dir = Join-Path $root "t11"
    $r = Invoke-Scenario -Branch "topic" -Commit $commitC -Dir $dir
    Assert-True ($null -eq $r.Error) -Label "install succeeds from the branch archive (error: $($r.Error))"
    Assert-Equal -Expected "b" -Actual (Get-FileText (Join-Path $dir "f.txt")) -Label "the files come from the branch archive"
    Assert-True (($messages | Where-Object { $_ -like "WARN:*archive for the pinned ref was not available*topic*" }).Count -eq 1) -Label "says which archive was installed instead"
    Assert-Equal -Expected 0 -Actual (@(Get-InstallerTempFiles | Where-Object { $tempBefore -notcontains $_ })).Count -Label "temp files are cleaned up"

    Write-Host ""
    Write-Host "-- ZIP fallback, no archive available --"
    $archives = @{}
    $dir = Join-Path $root "t12"
    $r = Invoke-Scenario -Branch "topic" -Commit $commitC -Dir $dir
    Assert-True (($null -ne $r.Error) -and ($r.Error -like "*Failed to download repository*")) -Label "the install fails with the download error (error: $($r.Error))"
    Assert-Equal -Expected 0 -Actual (@(Get-InstallerTempFiles | Where-Object { $tempBefore -notcontains $_ })).Count -Label "temp files are cleaned up"
    $failClones = $false
    Remove-Item function:git, function:Invoke-WebRequest -ErrorAction SilentlyContinue
} finally {
    foreach ($name in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name]) }
    Set-Location $repoRoot
    Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue
}

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
Write-Host ""
if ($failures -gt 0) {
    Write-Host "FAILED: $failures assertion(s) failed" -ForegroundColor Red
    exit 1
} else {
    Write-Host "All repository-pin tests passed." -ForegroundColor Green
    exit 0
}

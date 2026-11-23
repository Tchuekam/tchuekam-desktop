# TchueKAM Desktop v0.15.3 — Government & Enterprise IT Deployment Sheet

This runbook covers silent installation, cryptographic verification, Authenticode code-signing trust, air-gapped offline AI model seeding, and workstation policy configuration for deploying **TchueKAM Desktop v0.15.3** across government ministries and enterprise Windows fleets.

---

## 1. Distribution Package & Offline Bundle Layout

The staged air-gapped bundle (`apps/desktop/release/gov-offline-bundle/`) contains:

```text
gov-offline-bundle/
├── Install-TchuekamOffline.ps1                 # Turnkey silent installer + SHA-256 verifier + offline model seeder
├── SHA256SUMS.txt                              # Cryptographic SHA-256 manifest for every file in the bundle
├── bundle-manifest.json                        # Machine-readable inventory (paths, byte lengths, SHA-256 hashes)
├── installers/
│   ├── TchueKAM-Setup.exe                      # Windows x64 NSIS installer (supports /S silent install & /D=<path>)
│   ├── Tchuekam-Setup-win-x64.msi              # Windows x64 MSI package (for GPO / Intune / SCCM deployment)
│   ├── TchueKAM-Setup.exe.blockmap             # Differential auto-update blockmap
│   ├── latest.yml                              # electron-updater release feed metadata
│   └── Tchuekam-Enterprise-CodeSigning.cer     # Enterprise Authenticode public certificate for GPO trust rollout
└── offline-models/
    ├── bin/
    │   ├── uv.exe                              # Offline Python environment & package tool
    │   ├── uvw.exe
    │   └── uvx.exe
    ├── business-agent/
    │   ├── config.json                         # Default 2 GB low-RAM offline model configuration
    │   ├── models/
    │   │   ├── Qwen3-0.6B-Q4_K_M.gguf          # 378 MB FR/EN bilingual local GGUF model (~400 MB RAM)
    │   │   └── SmolLM2-360M-Instruct-Q4_K_M.gguf # 258 MB ultra-light local GGUF model (~335 MB RAM)
    │   └── runtime/
    │       ├── llama-server.exe                # Local CPU inference server (127.0.0.1 loopback only)
    │       └── *.dll                           # CPU SIMD kernels (SSE4.2 / AVX2 / Alderlake / Skylake / Zen4)
    └── models/
        └── kokoro/
            ├── kokoro-v1.0.int8.onnx           # 88 MB local neural TTS model (FR/EN voice synthesis)
            └── voices-v1.0.bin                 # 27 MB voice embeddings
```

---

## 2. Workstation Hardware Tiers

| Tier | System RAM | Recommended Local Model | Context / Thread Budget | Notes |
|---|---|---|---|---|
| **Tier 1 (Low-RAM PC)** | 2 GB – 3.5 GB | `SmolLM2-360M-Instruct-Q4_K_M.gguf` or `Qwen3-0.6B-Q4_K_M.gguf` | `1024` ctx, single-slot (`-np 1`), auto-unload after 180s idle | Automatically detected by `detectHardwareProfile()` (`totalRamMb <= 3584`); uses `0 MB` RAM when idle. |
| **Tier 2 (Standard Office PC)** | 4 GB – 8 GB | `Qwen3-0.6B-Q4_K_M.gguf` (FR/EN) | `1024`–`2048` ctx, reserves UI CPU headroom | Instant offline document drafting, CV/Invoice/Deck audit, and Kokoro TTS. |
| **Tier 3 (Power Workstation)** | 16 GB+ | `Qwen3-0.6B-Q4_K_M.gguf` + MbowaGPT / Ollama local runtime | Full multi-tool local + hybrid execution | Supports concurrent local voice + multi-agent pipelines. |

---

## 3. Turnkey Air-Gapped Installation (Recommended for Gov IT)

From an elevated or standard PowerShell prompt inside `gov-offline-bundle/`:

```powershell
# 1. Verify all SHA-256 hashes, trust the enterprise certificate, seed offline models, and silently install:
powershell.exe -ExecutionPolicy Bypass -File .\Install-TchuekamOffline.ps1 -TrustCertificate

# 2. Or deploy system-wide using the MSI package (for SCCM / Intune / GPO computer startup scripts):
powershell.exe -ExecutionPolicy Bypass -File .\Install-TchuekamOffline.ps1 -UseMsi -TrustCertificate

# 3. Or install silently into a custom directory via NSIS:
powershell.exe -ExecutionPolicy Bypass -File .\Install-TchuekamOffline.ps1 -InstallDir "C:\Apps\Tchuekam"
```

### Direct Silent Installer Commands (Without Wrapper Script)

- **MSI Silent Install (Per-Machine / GPO / Intune):**
  ```powershell
  msiexec.exe /i "Tchuekam-Setup-win-x64.msi" /qn /norestart /L*v "C:\Windows\Temp\tchuekam-install.log"
  ```
- **NSIS Silent Install (Per-User or Custom Directory):**
  ```powershell
  # Default per-user install (%LOCALAPPDATA%\Programs\Tchuekam):
  .\TchueKAM-Setup.exe /S

  # Custom target directory (/D= must be the last parameter, unquoted):
  .\TchueKAM-Setup.exe /S /D=C:\Apps\Tchuekam
  ```

---

## 4. Code Signing, SmartScreen & AppLocker / WDAC Policies

### Option A — Internal Ministry / Enterprise PKI Rollout (Included Certificate)
The packaged binaries (`Tchuekam.exe`, `TchueKAM-Setup.exe`, `Tchuekam-Setup-win-x64.msi`) are signed via `apps/desktop/scripts/sign-windows-artifacts.ps1` using SHA-256 Authenticode (`CN=TchuekaM Enterprise Code Signing, O=TchuekaM, C=CM`).

To trust this signature across domain-joined government workstations without public internet CA validation:
1. Open **Group Policy Management (`gpmc.msc`)** -> Edit target GPO -> **Computer Configuration → Policies → Windows Settings → Security Settings → Public Key Policies**.
2. Import `installers\Tchuekam-Enterprise-CodeSigning.cer` into:
   - **Trusted Root Certification Authorities**
   - **Trusted Publishers**
3. Or deploy via PowerShell as Administrator:
   ```powershell
   Import-Certificate -FilePath .\installers\Tchuekam-Enterprise-CodeSigning.cer -CertStoreLocation Cert:\LocalMachine\Root
   Import-Certificate -FilePath .\installers\Tchuekam-Enterprise-CodeSigning.cer -CertStoreLocation Cert:\LocalMachine\TrustedPublisher
   ```
4. Verify signature status on any endpoint:
   ```powershell
   Get-AuthenticodeSignature .\installers\TchueKAM-Setup.exe, .\installers\Tchuekam-Setup-win-x64.msi
   ```

### Option B — Public Internet Release (OV / EV Certificate or Azure Trusted Signing)
For unmanaged public Windows PCs outside an enterprise domain (where Windows Defender SmartScreen requires a commercial Microsoft Root Program CA):
- Re-sign the artifacts with your commercial OV/EV hardware token or PFX:
  ```powershell
  .\apps\desktop\scripts\sign-windows-artifacts.ps1 -Thumbprint "<YOUR_OV_EV_CERT_THUMBPRINT>" -TimestampServer "http://timestamp.digicert.com"
  ```
- Or run the GitHub Actions workflow `.github/workflows/build-windows-installer.yml` configured with Azure Trusted Signing secrets (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_CODE_SIGNING_ENDPOINT`, `AZURE_CODE_SIGNING_ACCOUNT`, `AZURE_CERT_PROFILE_NAME`).

---

## 5. Network, Firewall & Data Sovereignty Policy

- **Loopback-Only Binding**: Both the local Python backend (`127.0.0.1:9120–9199`) and the Business Hub `llama-server.exe` inference engine bind strictly to `127.0.0.1` (localhost). No inbound network port is exposed to the LAN.
- **Strict Air-Gapped Mode (`HERMES_OFFLINE=1`)**:
  Set system or user environment variable `HERMES_OFFLINE=1` on air-gapped workstations. When set:
  - Remote `/models` metadata probes short-circuit immediately with zero outbound sockets.
  - Business Hub document drafting, AI audit, template translation, PDF/DOCX/XLSX/PPTX export, and local GGUF + Kokoro voice synthesis operate 100% offline.

---

## 6. Clean-Machine Verification & Rollback / Uninstall

- **Verify Installed Binary & Version**:
  ```powershell
  (Get-Item "$env:LOCALAPPDATA\Programs\Tchuekam\Tchuekam.exe").VersionInfo | Select-Object ProductName, FileVersion, ProductVersion
  ```
- **Silent Uninstall (NSIS)**:
  ```powershell
  & "$env:LOCALAPPDATA\Programs\Tchuekam\Uninstall Tchuekam.exe" /S
  ```
- **Silent Uninstall (MSI)**:
  ```powershell
  msiexec.exe /x "Tchuekam-Setup-win-x64.msi" /qn /norestart
  ```

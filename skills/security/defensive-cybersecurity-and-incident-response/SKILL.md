---
name: defensive-cybersecurity-and-incident-response
description: Defensive security analysis, codebase and infrastructure vulnerability assessment, secret and dependency auditing, security monitoring, incident investigation, and system hardening.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [cybersecurity, defensive-security, vulnerability-assessment, incident-response, hardening]
    related_skills: [oss-forensics, web-pentest]
---

# Defensive Cybersecurity, Vulnerability Assessment & Incident Investigation

Use this skill for defensive cybersecurity operations, security audits, vulnerability assessments, incident forensics, and infrastructure protection (optimized for **MbowaGPT Cybertrunk**).

## Defensive Security Protocol

1. **Attack Surface & Codebase Audit**
   - Use `search_files` and `read_file` to inspect authentication boundaries, input validation, SQL/command construction, deserialization, CORS/CSRF policies, and file-path handling (path traversal / symlink checks).
   - Scan for hardcoded secrets, tokens, private keys, or exposed `.env` files before commits or deployments.

2. **Dependency & Supply-Chain Integrity**
   - Verify that all package manifests (`pyproject.toml`, `package.json`, `requirements.txt`, GitHub Actions workflows) enforce version upper bounds, lockfile hashes, and pinned commit SHAs.

3. **Host, Network & Log Forensics**
   - Use `terminal` and `process` (read-only diagnostic commands) to inspect active listening ports, process trees, file permissions, service configurations, and error/audit logs.
   - Classify findings by severity (**Critical**, **High**, **Medium**, **Low**, **Informational**) with exact file/line evidence (`file:line`), exploitability prerequisites, and concrete remediation patches.

4. **Verification**
   - When applying security fixes via `patch` or `write_file`, run automated tests to confirm the vulnerability is closed without breaking legitimate functionality.

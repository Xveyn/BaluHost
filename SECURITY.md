# Security Policy

## Supported Versions

Only the latest minor release line receives security updates. BaluHost follows semantic versioning — patch releases (`1.30.x`) carry security fixes for the current minor.

| Version | Supported |
| ------- | --------- |
| 1.30.x  | ✅        |
| < 1.30  | ❌        |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

Instead, report them privately via one of these channels:

- **GitHub Security Advisories** (preferred): Open a draft advisory at
  <https://github.com/Xveyn/BaluHost/security/advisories/new>
- **Email**: Contact the maintainer via the address listed on the [Xveyn GitHub profile](https://github.com/Xveyn)

Please include as much of the following as possible:

- Type of issue (e.g. path traversal, auth bypass, RCE, SSRF, information disclosure)
- Affected component (backend route, frontend page, service module, version)
- Full paths of source files related to the issue
- Step-by-step reproduction instructions
- Proof-of-concept or exploit code (if available)
- Impact assessment — what can an attacker achieve?

This information helps triage and fix the issue faster.

## Response Timeline

BaluHost is maintained by a single developer in spare time. Best-effort targets:

| Stage               | Target     |
| ------------------- | ---------- |
| Initial response    | 72 hours   |
| Triage & severity   | 7 days     |
| Fix for high/critical | 14 days  |
| Coordinated disclosure | after fix is released |

If you do not receive a response within 7 days, please send a reminder — the report may have been missed.

## Disclosure Policy

BaluHost follows **coordinated disclosure**:

1. You report the vulnerability privately.
2. We confirm the issue and develop a fix on a private branch.
3. A patched release is published.
4. After users have had reasonable time to update (typically 14 days), the advisory is made public.
5. Reporters are credited in the advisory unless they prefer to remain anonymous.

## Scope

In scope:

- `backend/app/` — FastAPI application, auth, file operations, services
- `client/src/` — React frontend
- Default configuration shipped with the project
- GitHub Actions workflows in `.github/workflows/`

Out of scope:

- Vulnerabilities in third-party dependencies — report those upstream first; we will bump affected dependencies as fixes land
- Social engineering or physical attacks
- Denial-of-service attacks that require abnormal traffic volume
- Issues in development/dev-mode (`NAS_MODE=dev`) that do not affect production
- Self-XSS or attacks requiring an already-compromised victim account

## Security Posture

For context on BaluHost's current security invariants, accepted risks, and threat model, see `.claude/rules/security-agent.md` in this repository. Known gaps are documented there and in `PRODUCTION_READINESS.md`.

# BaluHost Companion App — Install & Use

The BaluHost Companion is a small desktop app that runs **on the BaluNode itself** and is the only way to perform irreversible admin operations (RAID destroy, plugin install, VPN key rotation, user bulk-delete, initial setup wizard).

## Why it exists

A few admin endpoints are gated behind a **local channel** check — the request must arrive via the Unix socket `/run/baluhost/local.sock`, which is reachable only by processes running as the `baluhost` OS user. JWT auth is still required; this is a second factor that requires physical presence.

If you try one of these actions from the Web UI on a remote browser, the button is disabled with a lock icon and the tooltip "Only available via the BaluHost Companion app running on the server itself."

## Install

1. Download the `.deb` from the BaluHost Releases page (matching your BaluHost version).
2. Install: `sudo apt install ./baluhost-companion_*.deb`
3. Add your interactive user to the `baluhost` group: `sudo usermod -aG baluhost $USER`
4. **Log out and back in** for group membership to take effect.
5. Launch from the application menu (KDE: search for "BaluHost Companion") or from the terminal: `baluhost-companion`.

## First-time setup

If your BaluHost is freshly installed (no admin user yet), the Companion app opens directly into the setup wizard. Create the first admin, optionally a regular user, choose your file-sharing protocols (Samba/WebDAV), and finish. The Web UI on the same machine will then accept the new admin's login.

## Daily use

Open the Companion when you need to perform an irreversible operation. For everything else, the Web UI in your browser works fine and is the recommended interface.

## Troubleshooting

**"Cannot connect to baluhost-backend-local.service"** — verify the service is running:

```bash
systemctl status baluhost-backend-local.socket baluhost-backend-local.service
```

If the socket is up but the service hasn't started, that's normal — it's socket-activated and starts on first connection.

**"Channel: remote" in the Web UI even on the BaluNode browser** — that's expected. The Web UI uses the TCP port (via nginx); only the Companion app uses the Unix socket. To verify your install is OK, open the Companion app.

**Permission denied connecting to socket** — your user is not in the `baluhost` group, or you haven't logged out/in since `usermod`. Check: `groups | grep baluhost`.

## See also

- `.claude/rules/ci-cd-security.md` — the trust model behind the local channel
- `docs/superpowers/specs/2026-05-25-tauri-local-admin-design.md` — full design doc

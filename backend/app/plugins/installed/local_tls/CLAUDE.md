# local_tls Plugin ("Feste Adresse im Heimnetz")

Bundled (in-process, fully trusted) plugin, **off by default** like every bundled
plugin (the manager only loads `installed_plugins` rows with `is_enabled`, and
discovery creates none). It keeps a DNS name (v1: DuckDNS) on the box's LAN IP and
obtains/renews a Let's Encrypt certificate for it via `lego` (DNS-01). nginx serves
the certificate from `<data>/live/`. Design:
`docs/superpowers/specs/2026-11-25-local-tls-plugin-design.md`.

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md`.

## Layout

| File | Contents |
|---|---|
| `__init__.py` | `LocalTlsPlugin` — metadata/permissions, config schema, two background tasks, notification specs, lazy `get_router()` |
| `config.py` | `LocalTlsConfig` (domain, provider, interface, email, staging) — validated in the schema; values that start with `-` are rejected because they end up as argv |
| `service.py` | `run_address_check`, `run_cert_check`, `get_status`, `deliver`, `run_check` (thread + own DB session + delivery, never raises in the background) |
| `state.py` | The one row of `local_tls_state` (`app/models/local_tls_state.py`); token encrypt/decrypt |
| `providers/` | DNS provider adapters (`base.py` rules, `duckdns.py`), registry in `__init__.py` |
| `address.py` | LAN IP via `ip -j` (private IPv4 only) |
| `lego.py` | The **only** contact with lego (list args, timeout 300 s, credentials only via `env`) |
| `deploy_cert.py` | Inspect, atomic `live` symlink swap, nginx reload, served-certificate verification |
| `paths.py` | `DATA_DIR`, `ensure_dirs`, the run lock `<data>/.lock` |
| `routes.py` | Admin routes (status, token, manual runs) |

## Flow

- `address_check` every 300 s: LAN IP → `update_address` when it changed, when
  forced, or when the last set is ≥ 86400 s old (daily reconfirm). `address_changed`
  only when a previous IP existed and differs.
- `cert_check` every 86400 s (and on startup): lego version ≥ 4.35 → `obtain_or_renew`
  (`run` if no cert, else `renew --days 30`) → on a new cert (or `force`) `deploy`.
  `DeployOutcome.served=False` (installed, nginx not yet switched to `live/`) is a
  **success** with reason "installiert, nginx liefert es noch nicht aus". Afterwards,
  independently: installed cert expires in ≤ 21 days → `cert_expiring`.
- Checks return `PendingEvent`s; they are sent **after** booking via
  `emit_plugin_event`, which enforces the declared cooldowns (entity = domain).
  So the checks stay synchronous and run in `asyncio.to_thread`.
- Both checks take the same lock. Background runs skip on `AlreadyRunning`
  (`raise_if_running=False`); manual routes pass `True` and map it to 409.
- On failure `record_renew` keeps the previous fingerprint/expiry — the installed
  certificate has not changed.

## Invariants

- **No new sudoers rule.** nginx reload only via the existing
  `sudo -n /usr/bin/systemctl reload nginx`. No certbot, no lego as root.
- **Token:** Fernet via `VPNEncryption`, column `provider_secret` (matches
  `REDACT_PATTERN`). Never in responses, logs, audit, exception messages or
  `last_renew_reason`. A token that no longer decrypts (key missing/rotated) is a
  reported failure ("credentials unreadable"), never a crash. `run_check` logs an
  unexpected exception by **type only** — its message could contain the token.
- **Adapters:** HTTPS to the provider's own host only, timeout ≤ 15 s, no shell,
  no file access, domain and IP validated before every call, IP private IPv4.
- **Staging vs production:** separate lego state (`<data>/lego` vs
  `<data>/lego-staging`), so switching staging → production issues anew instead
  of a no-op `renew`.
- **nginx paths:** `<data>/live/fullchain.pem` and `<data>/live/privkey.pem`; `live`
  is a relative symlink to `releases/<UTC timestamp>/`; the last 3 releases stay.
  `<data>` is fixed at `/var/lib/baluhost/plugins/local_tls/` (dirs 0700, keys 0600).
- Background tasks run primary-only (framework); do not add a cross-worker guard.
- `routes.py` must not use `from __future__ import annotations` (slowapi body detection).

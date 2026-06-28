# Plugin Marketplace Index Signing (ed25519) — Track C

**Status:** Spec
**Date:** 2026-06-28
**Track:** Plugin-Sandboxing Track C — Provenance/Integrity (final strategic track after A: frontend iframe ✅, B: backend isolation ✅)
**Scope:** Backend verification of a detached ed25519 signature over the marketplace `index.json`; two deploy scripts (one-time public-key provisioning helper + a non-fatal per-deploy signature smoke-check); plus a documented companion checklist for the external `BaluHost-Plugin-Market` repo (CI signing + key). No installer change, no frontend change, no new sudoers entry, no new GitHub secret.

## Problem

The marketplace trust chain has a self-referential gap. `MarketplaceService.get_index()` (`backend/app/services/plugin_marketplace.py:116`) fetches `index.json` over HTTPS from `settings.plugins_marketplace_index_url` (the external Plugin-Market repo, served via GitHub Pages). Each version entry carries `download_url` + `checksum_sha256` (`backend/app/plugins/marketplace.py:20`), and the installer verifies every downloaded archive against that checksum (`backend/app/plugins/installer.py:206`, `_verify_checksum`).

But the checksum lives in the **same index** it vouches for. TLS stops a pure wire-MITM, yet a compromised GitHub Pages host, a tampered index repo, or anyone with write access to the published `dist/` controls *both* the archive and its checksum — so there is no provenance anchor independent of the hosting. A tampered index → attacker-chosen archive with a matching checksum → code installed into the (sandboxed, but still executing) external-plugin runtime.

The existing marketplace spec (`docs/superpowers/specs/2026-04-13-plugin-marketplace-design.md`) explicitly deferred signing: *"Plugin signing in v1. v1 verifies SHA-256 checksums from the index. Cryptographic signatures are tracked as a follow-up."* This spec is that follow-up.

## Goals

- A detached **ed25519 signature** over the raw `index.json` bytes, verified by the backend before the index is parsed or trusted.
- The signature is the new trust anchor; archive integrity stays transitively covered via the now-signed `checksum_sha256` (no installer change).
- **Fail-closed from day one:** an unsigned or invalidly-signed index is rejected (the admin-only Marketplace tab shows an error instead of listings). No transitional warn-only window.
- **Rotation-friendly:** the backend trusts a *list* of public keys (mirrors the existing MultiFernet dual-key pattern), so a key can be rotated without breaking installs.
- **Fork-friendly (#207):** the trusted public key(s) and signature URL are config values, env-overridable, so a fork can point at its own market with its own key. The code ships with an **empty** key default; upstream and forks alike supply their key out-of-band (env / deploy-time edit) — see *Key Provisioning*.
- **Operationally automated:** a one-time idempotent provisioning helper sets the public key into `.env.production` from a server-side key file (no hand-editing), and a non-fatal per-deploy smoke-check verifies the live index signature on every deploy — surfacing a broken/forgotten signing setup in the deploy log instead of only when an admin opens the Marketplace tab.

## Non-Goals

- **Per-author / per-artifact signatures (TUF-like).** A single marketplace key signs the index; archives are covered transitively. Per-author provenance is unjustified at the current scale (one solo-curated official index).
- **Embedded-in-JSON signatures.** Rejected — JSON canonicalization (field order / whitespace) is a classic source of subtle verify bugs. We sign and verify the raw bytes.
- **TUF / online key-revocation infrastructure.** Rotation = edit the trusted-key list + redeploy. No revocation server.
- **Signing of bundled plugins.** They ship in-repo as part of the release and are already trusted (Track B trust tiers).
- **Changing the installer's checksum verification.** `_verify_checksum` stays — it is the transitive integrity link from the signed index to the archive.
- **Frontend changes.** The Marketplace tab consumes the same `/api/plugins/marketplace` response shape; only its error path (already a 502 toast) is exercised more.

## Architecture

```
BaluHost-Plugin-Market (Git repo)                    BaluHost backend
─────────────────────────────────                    ────────────────
CI publish.yml:                                       MarketplaceService.get_index():
  build index.json                                      raw = fetch(index_url)            (existing)
  sign_index.py index.json $KEY  ──► index.json.sig     sig = fetch(signature_url)         NEW
  publish index.json + index.json.sig (GitHub Pages)    verify_detached_ed25519(           NEW, fail-closed
        │                                                  raw, sig, trusted_pubkeys)
        │   private key = GitHub Actions secret           json.loads(raw) + schema          (existing)
        ▼                                                      │
   public key  ───────baked into──────►  settings.plugins_marketplace_public_keys (default)
                                                               ▼
                                          Installer: download → _verify_checksum(checksum_sha256)  (UNCHANGED)
```

The signature is verified over the **exact raw bytes** of `index.json`, *before* `json.loads`. This avoids any canonicalization concern: the CI signs the same bytes it publishes.

## Components

### `app/plugins/signing.py` (NEW — pure, isolated, the testable unit)

```python
def verify_detached_ed25519(
    message: bytes,
    signature_b64: str,
    public_keys_b64: Sequence[str],
) -> None:
    """Verify a detached ed25519 signature against any trusted key.

    Raises SignatureError if: the key list is empty; signature_b64 or any
    key is not valid base64 / not a 32-byte key / not a 64-byte signature;
    or no trusted key validates the signature over `message`.
    Returns None on the first key that validates.
    """
```

- Uses `cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PublicKey` (already a dependency — used for Fernet/crypto-at-rest).
- `SignatureError(Exception)` defined here.
- Empty `public_keys_b64` → `SignatureError` (a misconfigured backend must fail closed, never accept).
- Each public key is base64 of the 32 raw public-key bytes; signature is base64 of the 64 raw signature bytes.

### `MarketplaceService` (MODIFY — `backend/app/services/plugin_marketplace.py`)

- Constructor gains `public_keys: Sequence[str]` and `signature_url: Optional[str] = None` (default derived as `index_url + ".sig"`). The existing `index_fetcher` is reused to fetch the `.sig` (same host, same httpx client semantics) — no second fetcher injection needed; tests inject one fetcher that serves both URLs.
- New `IndexSignatureError(MarketplaceError)`.
- In `get_index()`, immediately after `raw = self._fetch(self._index_url)`:
  ```python
  try:
      sig = self._fetch(self._signature_url)
  except Exception as exc:
      raise IndexSignatureError(f"failed to fetch index signature from {self._signature_url}: {exc}") from exc
  try:
      verify_detached_ed25519(raw, sig.decode("ascii").strip(), self._public_keys)
  except SignatureError as exc:
      raise IndexSignatureError(f"index signature verification failed: {exc}") from exc
  # ... then json.loads(raw) as today
  ```
- Cache/TTL/`invalidate_cache`/`refresh` semantics unchanged: a stale cache or `force_refresh` re-fetches *and* re-verifies before re-caching. The cached object is always a verified index.
- `install()` looks up the entry via `get_index()` (cached, verified) → its `checksum_sha256` is therefore signed-trusted. No install-time signature step needed.

### Route (MODIFY — `backend/app/api/routes/plugins_marketplace.py`)

- `list_marketplace` maps `IndexSignatureError` → `HTTP_502_BAD_GATEWAY`, client detail scrubbed to `"marketplace index signature verification failed"`; the underlying exception is logged at warning, never returned (consistent with the existing `IndexFetchError`/`IndexParseError` handling and the Posten-2 error-leakage policy).

### Config (MODIFY — `backend/app/core/config.py`)

- `plugins_marketplace_public_keys: list[str]` — base64 ed25519 public keys. **Default `[]` (empty).** Chosen approach (see *Key Provisioning* below): the code ships with no baked-in key; the maintainer fills the real public key before deploy. An empty list is self-documenting fail-closed — `verify_detached_ed25519` raises on an empty key list, so an unconfigured backend rejects every index (Marketplace listing returns 502) until a key is supplied. Env-overridable (`PLUGINS_MARKETPLACE_PUBLIC_KEYS`) for forks and for the upstream deploy. **Env representation:** a JSON array of base64 strings (Pydantic Settings' default parse for `list[str]`), e.g. `PLUGINS_MARKETPLACE_PUBLIC_KEYS=["<b64key>"]` — the provisioning helper emits exactly this form.
- `plugins_marketplace_signature_url: Optional[str] = None` — default None → service derives `index_url + ".sig"`. Override available if a fork hosts the sig elsewhere.
- `get_marketplace_service()` passes both into `MarketplaceService(...)`.

### Key Provisioning (chosen approach: defer, fill before deploy)

The signing keypair lives entirely **outside** code, this session, and git — the private key is the root of Track C's trust and must never touch the AI session transcript or the repo. Therefore:

- The PR ships `plugins_marketplace_public_keys` with an **empty default** — no placeholder string, no real key.
- The maintainer generates the keypair **offline** (own trusted machine), stores the private key as the Plugin-Market GitHub secret, and supplies the public key to the upstream deploy via **env var** (`PLUGINS_MARKETPLACE_PUBLIC_KEYS`) on `.env.production`, or by a one-line edit to the config default at deploy time.
- Until both (a) the public key is configured and (b) the live index is signed, the admin-only Marketplace listing is fail-closed (502). On the greenfield deployment (0 external plugins) this affects only the listing, never a running plugin.

### Deploy Automation (provisioning helper + per-deploy smoke-check)

Two scripts remove the manual `.env.production` edit and surface signing health on every deploy. Neither needs a GitHub secret (the public key is not secret) nor a new sudoers entry (see invocation notes).

**1. Provisioning helper — `deploy/scripts/install-marketplace-pubkey.sh` (NEW, one-time / on rotation).**
- Reads the base64 public key(s) from a server-side file (default `/etc/baluhost/marketplace-pubkey.b64`, override via `$MARKETPLACE_PUBKEY_FILE`), one base64 key per non-empty / non-`#` line. The maintainer drops this file on the box (server access) — public material only.
- Validates each line is base64 of exactly 32 bytes (a valid ed25519 public key) and **fails loudly** on a bad key rather than writing one that would silently fail-close the marketplace.
- Builds the JSON-array env value and **idempotently** sets `PLUGINS_MARKETPLACE_PUBLIC_KEYS=[...]` in `/opt/baluhost/.env.production`: replace the line if present, append if absent, no-op if already identical. Preserves the file's `600` / `baluhost:baluhost` mode+owner.
- **Invocation:** run once manually as root at setup, and again when rotating keys (drop a new file, re-run). It is intentionally **not** wired into the routine deploy — the key persists across deploys, so re-asserting it every time adds a sudoers entry for no benefit. (Wiring it behind the existing `SYNC_PERMISSIONS` opt-in block in `ci-deploy.sh` is a possible later convenience, but would require a deploy-sudoers allowlist entry; deferred.)

**2. Per-deploy smoke-check — backend entrypoint + `ci-deploy.sh` step (NEW, every deploy, non-fatal).**
- Backend module `app/plugins/verify_index_signature.py` with a `__main__`: loads `settings`, fetches the live `index.json` + its `.sig` (httpx), runs the shared `verify_detached_ed25519`, prints a one-line `PASS` / `WARN: <reason>`, and **always exits 0** (a signing hiccup must never fail a healthy deploy). Reuses the exact verification code path (DRY) — no second implementation.
- Distinguishes: key not configured (`WARN: marketplace signing not configured`), index/sig unreachable (`WARN: …`), signature invalid (`WARN: signature verification failed` — the one that matters).
- `ci-deploy.sh`: after the success-path health check, a new non-fatal step runs `"$VENV_BIN/python" -m app.plugins.verify_index_signature` (env already exported by `load_env_production`) and logs its line. Mirrors the existing non-fatal opt-in steps' style (`|| log_warn …`); never triggers rollback. Always-on (not behind `SYNC_PERMISSIONS`) — verification is the genuinely per-deploy concern.

### Companion: `BaluHost-Plugin-Market` repo (documented checklist — executed by the maintainer, not by this PR)

1. **Generate the keypair once, offline:**
   ```python
   from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
   from cryptography.hazmat.primitives import serialization
   import base64
   sk = Ed25519PrivateKey.generate()
   raw_priv = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
   raw_pub  = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
   print("PRIVATE (secret):", base64.b64encode(raw_priv).decode())
   print("PUBLIC  (bake in):", base64.b64encode(raw_pub).decode())
   ```
2. Store the **private** key as the GitHub Actions secret `MARKETPLACE_SIGNING_KEY`. Bake the **public** key into the BaluHost config default (and document it in this spec's follow-up / the market repo README).
3. Add `scripts/sign_index.py` (mirror of the verify logic): reads `index.json`, signs the raw bytes with the secret key, writes `index.json.sig` (base64 of the 64-byte signature).
4. Update `publish.yml`: after building `index.json`, run `sign_index.py`, then publish **both** `index.json` and `index.json.sig` to GitHub Pages.

## Key Rotation

`plugins_marketplace_public_keys` is a list. To rotate: (1) generate a new keypair; (2) add the new public key to the list and ship/redeploy BaluHost (now trusts old + new); (3) switch the market CI to sign with the new private key and re-publish; (4) once all installs run the updated backend, drop the old public key. No downtime, no install breakage.

## Rollout Sequence (fail-closed, order matters)

1. Generate the keypair (offline).
2. Plugin-Market repo: add the `MARKETPLACE_SIGNING_KEY` secret + `sign_index.py` + CI step → `index.json.sig` is **live** alongside `index.json`.
3. BaluHost: bake the public key into the config default + land the backend verification (fail-closed) — this PR.
4. Deploy the backend.

The signature must be live (step 2) **before** the backend enforces (step 4), or the Marketplace tab returns 502. Because the deployment is greenfield (0 external plugins installed), even a sequencing gap affects only the admin-only Marketplace *listing*, never a running plugin.

## Error Handling

- Missing/unfetchable `.sig` → `IndexSignatureError` → 502 (fail-closed; never fall back to unsigned).
- Invalid signature / untrusted key / malformed base64 → `IndexSignatureError` → 502.
- Empty trusted-key list (misconfiguration) → `SignatureError` → `IndexSignatureError` → 502.
- All client-facing details scrubbed; full reason logged at warning.

## Testing

**`backend/tests/plugins/test_signing.py` (NEW)** — generates a throwaway ed25519 keypair in-test (no real key committed):
- Valid signature over the message → passes.
- Tampered message (flip a byte) → `SignatureError`.
- Wrong/untrusted key → `SignatureError`.
- Rotation: two trusted keys, signature made with the second → passes.
- Empty key list → `SignatureError`.
- Malformed base64 signature / malformed key → `SignatureError`.

**`backend/tests/plugins/test_plugin_marketplace_service.py` (EXTEND)** — the existing fake fetcher serves both `index.json` and `index.json.sig`:
- `get_index()` verifies the signature and returns the parsed index when valid.
- Missing `.sig` → `IndexSignatureError`.
- Invalid signature → `IndexSignatureError`.
- Cache still works (verified index cached; re-fetch on TTL re-verifies).

**`backend/tests/api/test_plugins_marketplace_routes.py` (EXTEND)** — signature failure surfaces as a scrubbed 502.

**`backend/tests/plugins/test_verify_index_signature.py` (NEW)** — the smoke-check entrypoint's logic (factored into a testable function returning a `(ok, message)` result, with the `__main__` only printing + exiting 0): valid live index → PASS; empty key → `WARN: marketplace signing not configured`; fetch failure (injected fetcher raises) → WARN; invalid signature → WARN. Inject the fetcher; no network. Assert the function never raises (the entrypoint must be crash-proof).

The two **shell scripts** (`install-marketplace-pubkey.sh`, the `ci-deploy.sh` step) are validated with `bash -n` (syntax) plus a focused unit test of the helper's idempotent line-edit on a temp `.env` fixture if practical; their live behavior is covered by manual smoke on the box (consistent with how the other `deploy/scripts/install-*.sh` are handled).

All Python tests run cross-platform (pure crypto + in-memory fetchers; no network, no real keys).

## Decomposition & Rollout

One cohesive PR on a branch off `main`. Suggested task order:
1. `signing.py` + `test_signing.py` (the pure verify unit, TDD).
2. `MarketplaceService` wiring + `IndexSignatureError` + service tests.
3. Config settings + `get_marketplace_service()` threading + route 502 mapping + route test.
4. Smoke-check entrypoint `app/plugins/verify_index_signature.py` + `test_verify_index_signature.py`, then wire the non-fatal step into `ci-deploy.sh` (`bash -n`).
5. Provisioning helper `deploy/scripts/install-marketplace-pubkey.sh` (idempotent line-edit + base64/32-byte validation; `bash -n` + temp-`.env` unit check).

The companion `BaluHost-Plugin-Market` changes (keypair, `sign_index.py`, CI, secret) are a separate operator checklist (above), sequenced before the backend deploy. The config default ships **empty** (chosen approach: defer); the real public key is supplied out-of-band via the provisioning helper reading a server-side key file → `PLUGINS_MARKETPLACE_PUBLIC_KEYS` on `.env.production` — never committed.

Note: tasks 4–5 touch `deploy/` (CODEOWNERS-protected) but add **no** sudoers entry and **no** GitHub secret; the helper is a manually-run root script and the smoke-check is a non-fatal venv-python invocation.

## Self-Review

- **Coverage:** verification point (get_index pre-parse), detached raw-ed25519, fail-closed, rotation list, fork config, companion CI, provisioning helper, per-deploy smoke-check, tests — all specified.
- **Consistency:** `IndexSignatureError(MarketplaceError)` mirrors `IndexFetchError`/`IndexParseError`; 502 mapping + scrubbing matches existing routes and the Posten-2 policy; trusted-key list mirrors MultiFernet; config env-override matches #207 fork model; the smoke-check + helper follow the existing `ci-deploy.sh` non-fatal-step / `deploy/scripts/install-*.sh` patterns; smoke-check reuses `verify_detached_ed25519` (no duplicate crypto).
- **Scope:** one PR — backend verify + 2 deploy scripts; documented external-repo checklist; no installer/frontend change, no new sudoers entry, no new GitHub secret.
- **Ambiguity:** signature is over raw bytes (no canonicalization); `.sig` is base64 of the 64-byte signature; public keys are base64 of 32 raw bytes; signature URL defaults to `index_url + ".sig"`.
- **Open operational item:** the actual upstream public key is generated out-of-band and supplied via env (`PLUGINS_MARKETPLACE_PUBLIC_KEYS`) at deploy; the code default stays empty (fail-closed until configured). The private key never enters code, git, or this session.

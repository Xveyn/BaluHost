# Plugin Marketplace Index Signing (ed25519) — Track C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify a detached ed25519 signature over the marketplace `index.json` before the backend trusts it (fail-closed), plus two deploy scripts: a one-time public-key provisioning helper and a non-fatal per-deploy signature smoke-check.

**Architecture:** A new pure module `app/plugins/signing.py` verifies a base64 detached ed25519 signature over the raw index bytes against a list of trusted base64 public keys. `MarketplaceService.get_index()` fetches `index.json` + `index.json.sig` and verifies before `json.loads` — a stale cache / refresh re-verifies. Archive integrity stays transitive via the already-signed `checksum_sha256` (no installer change). Config supplies the trusted keys (empty default → fail-closed). A deploy smoke-check reuses the same verify code; a provisioning helper sets the key into `.env.production`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic Settings, `cryptography` (already a dependency), pytest; Bash (deploy scripts).

## Global Constraints

- **`cryptography` is already a dependency** (used for Fernet) — do not add a new package. Use `cryptography.hazmat.primitives.asymmetric.ed25519`.
- **Sign/verify the RAW bytes** of `index.json` — never a re-serialized/canonicalized form. The `.sig` content is base64 of the 64-byte signature; public keys are base64 of the 32-byte raw key.
- **Fail-closed:** an empty trusted-key list, a missing/unfetchable `.sig`, or an invalid signature must reject the index (→ `IndexSignatureError` → 502). Never fall back to unsigned.
- **Env value MUST be single-quoted** when written to `.env.production`: `PLUGINS_MARKETPLACE_PUBLIC_KEYS='["<b64>"]'`. The value is consumed by bash `source` (ci-deploy.sh), systemd `EnvironmentFile`, and Pydantic — all three strip ONE layer of outer quoting and keep the inner JSON `"` intact. An unquoted `=["x"]` gets its inner quotes eaten by bash `source` and breaks JSON parsing.
- **Test fakes must be URL-aware.** The service fetches the index AND the `.sig` through the *same* fetcher. Existing fakes return the index for any URL — that returns index bytes for the `.sig` URL and breaks verification. Every fake must serve the index for the index URL and a (correctly-signed-by-the-test-key) signature for `index_url + ".sig"`, and the service must be built with the matching test public key.
- **Repo hook:** the Grep/Glob tools are blocked. Use Read / `mcp__vectordb-search__*`. Do NOT put the word `grep` (or `rg`) in any Bash tool command or its description — even inside a description it trips the hook. The deploy shell *script files* may use `grep` internally (they run on the server); just never invoke them via a Bash command string that itself contains `grep`.
- **Windows test runs:** the full backend suite can hang on Windows — run the **targeted** test files named in each task (`python -m pytest tests/plugins/test_signing.py -v`, etc.). The full suite can go to CI.
- **Commit footer.** Every commit message must end with exactly these two trailer lines (after a blank line); do NOT use `--no-verify`:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Qc4Ly7J5ALeCgujbKfs7FA
  ```
- **Branch:** `feat/plugin-marketplace-index-signing` (already created off `main`; the spec lives at `docs/superpowers/specs/2026-06-28-plugin-marketplace-index-signing-design.md`). Run backend commands from `backend/`.

---

## File Structure

- `backend/app/plugins/signing.py` — NEW: `verify_detached_ed25519` + `SignatureError`.
- `backend/tests/plugins/test_signing.py` — NEW: unit tests for the verify function.
- `backend/app/services/plugin_marketplace.py` — MODIFY: `IndexSignatureError`, constructor `public_keys`/`signature_url`, signature gate in `get_index()`, thread config in `get_marketplace_service()`.
- `backend/tests/plugins/test_plugin_marketplace_service.py` — MODIFY: URL-aware signed fakes + new signature tests.
- `backend/app/core/config.py` — MODIFY: two new settings fields.
- `backend/app/api/routes/plugins_marketplace.py` — MODIFY: map `IndexSignatureError` → 502 in the list and install routes.
- `backend/tests/api/test_plugins_marketplace_routes.py` — MODIFY: signed fakes + a scrubbed-502 test.
- `backend/app/plugins/verify_index_signature.py` — NEW: deploy smoke-check entrypoint (`check_index_signature` + `__main__`).
- `backend/tests/plugins/test_verify_index_signature.py` — NEW: smoke-check unit tests.
- `deploy/scripts/ci-deploy.sh` — MODIFY: non-fatal smoke-check step after the success-path health check.
- `deploy/scripts/install-marketplace-pubkey.sh` — NEW: idempotent public-key provisioning helper.

---

### Task 1: `signing.py` — detached ed25519 verify (pure unit, TDD)

**Files:**
- Create: `backend/app/plugins/signing.py`
- Test: `backend/tests/plugins/test_signing.py`

**Interfaces:**
- Consumes: `cryptography` only.
- Produces: `verify_detached_ed25519(message: bytes, signature_b64: str, public_keys_b64: Sequence[str]) -> None` and `SignatureError(Exception)` — used by Task 2 (`MarketplaceService`) and Task 4 (smoke-check).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_signing.py`:

```python
import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.plugins.signing import SignatureError, verify_detached_ed25519


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    sk = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(
        sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()
    return sk, pub_b64


def _sign(sk: Ed25519PrivateKey, message: bytes) -> str:
    return base64.b64encode(sk.sign(message)).decode()


def test_valid_signature_passes():
    sk, pub = _keypair()
    msg = b'{"index_version": 1}'
    verify_detached_ed25519(msg, _sign(sk, msg), [pub])  # no raise


def test_tampered_message_fails():
    sk, pub = _keypair()
    msg = b'{"index_version": 1}'
    sig = _sign(sk, msg)
    with pytest.raises(SignatureError):
        verify_detached_ed25519(msg + b" ", sig, [pub])


def test_wrong_key_fails():
    sk, _ = _keypair()
    _, other_pub = _keypair()
    msg = b"hello"
    with pytest.raises(SignatureError):
        verify_detached_ed25519(msg, _sign(sk, msg), [other_pub])


def test_rotation_second_key_validates():
    sk, pub = _keypair()
    _, old_pub = _keypair()
    msg = b"payload"
    verify_detached_ed25519(msg, _sign(sk, msg), [old_pub, pub])  # no raise


def test_empty_key_list_fails():
    sk, _ = _keypair()
    with pytest.raises(SignatureError):
        verify_detached_ed25519(b"x", _sign(sk, b"x"), [])


def test_malformed_signature_base64_fails():
    _, pub = _keypair()
    with pytest.raises(SignatureError):
        verify_detached_ed25519(b"x", "not!base64!!", [pub])


def test_malformed_key_fails():
    sk, _ = _keypair()
    with pytest.raises(SignatureError):
        verify_detached_ed25519(b"x", _sign(sk, b"x"), ["not!base64!!"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`): `python -m pytest tests/plugins/test_signing.py -v`
Expected: FAIL — `ModuleNotFoundError: app.plugins.signing` (module not created yet).

- [ ] **Step 3: Write the module**

Create `backend/app/plugins/signing.py`:

```python
"""Detached ed25519 signature verification for the marketplace index.

Given the raw signed bytes, a base64 detached signature, and a list of
trusted base64 ed25519 public keys, verify that *some* trusted key signed
the bytes. Used by the marketplace service (fail-closed index gate) and the
deploy smoke-check. Pure — no I/O.
"""
from __future__ import annotations

import base64
import binascii
from typing import Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class SignatureError(Exception):
    """Raised when a detached ed25519 signature cannot be verified."""


def verify_detached_ed25519(
    message: bytes,
    signature_b64: str,
    public_keys_b64: Sequence[str],
) -> None:
    """Verify ``signature_b64`` over ``message`` against any trusted key.

    Returns None on the first trusted key that validates. Raises
    ``SignatureError`` if the key list is empty, the signature is not valid
    base64 / not 64 bytes, or no trusted key validates the signature. A
    malformed key in the list is skipped, not fatal, unless it is the only
    reason nothing validated.
    """
    keys = list(public_keys_b64)
    if not keys:
        raise SignatureError("no trusted public keys configured")

    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SignatureError(f"signature is not valid base64: {exc}") from exc
    if len(signature) != 64:
        raise SignatureError(f"signature must be 64 bytes, got {len(signature)}")

    last_err = "no trusted key validated the signature"
    for key_b64 in keys:
        try:
            raw = base64.b64decode(key_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            last_err = f"public key is not valid base64: {exc}"
            continue
        if len(raw) != 32:
            last_err = f"public key must be 32 bytes, got {len(raw)}"
            continue
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(signature, message)
            return
        except InvalidSignature:
            last_err = "no trusted key validated the signature"
            continue

    raise SignatureError(last_err)
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `backend/`): `python -m pytest tests/plugins/test_signing.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/signing.py backend/tests/plugins/test_signing.py
git commit -F <msgfile>   # subject: "feat(plugin-market): detached ed25519 signature verify util" + footer
```

---

### Task 2: `MarketplaceService` signature gate + signed test fakes

**Files:**
- Modify: `backend/app/services/plugin_marketplace.py`
- Modify (test helpers + new tests): `backend/tests/plugins/test_plugin_marketplace_service.py`

**Interfaces:**
- Consumes: `verify_detached_ed25519` / `SignatureError` from Task 1.
- Produces: `IndexSignatureError(MarketplaceError)`; `MarketplaceService.__init__` gains keyword params `public_keys: Sequence[str]` and `signature_url: Optional[str] = None`. Task 3 (config threading + routes) and the route tests depend on these.

- [ ] **Step 1: Update the test helpers to serve a signed index, then add failing signature tests**

In `backend/tests/plugins/test_plugin_marketplace_service.py`:

(a) Add imports near the top (after the existing imports):

```python
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
```

(b) Add `IndexSignatureError` to the existing `from app.services.plugin_marketplace import (...)` block.

(c) Add a module-level test keypair + signer (after the imports, before `_build_plugin_zip`):

```python
_TEST_SK = Ed25519PrivateKey.generate()
_TEST_PUB_B64 = base64.b64encode(
    _TEST_SK.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode()


def _sign_index(index_raw: bytes) -> bytes:
    """base64 detached signature bytes, as the .sig file would contain."""
    return base64.b64encode(_TEST_SK.sign(index_raw))
```

(d) Replace the `_Fake` class with a URL-aware, signing version:

```python
class _Fake:
    """Captures an index JSON + archive map; serves index + .sig + archives."""

    INDEX_URL = "https://plugins.example/index.json"
    SIG_URL = "https://plugins.example/index.json.sig"

    def __init__(
        self,
        *,
        index: dict,
        archives: Dict[str, bytes],
        signature: bytes | None = None,
        sig_fetch_error: bool = False,
    ):
        self.index_raw = json.dumps(index).encode()
        self.archives = archives
        self.index_calls = 0
        self.sig_fetch_error = sig_fetch_error
        # Default: a valid signature by the test key. Tests can override with a
        # bogus value to exercise the rejection path.
        self.signature = signature if signature is not None else _sign_index(self.index_raw)

    def fetch_index(self, url: str) -> bytes:
        if url == self.SIG_URL:
            if self.sig_fetch_error:
                raise RuntimeError("sig unreachable")
            return self.signature
        self.index_calls += 1
        return self.index_raw

    def fetch_archive(self, url: str) -> bytes:
        if url not in self.archives:
            raise RuntimeError(f"unexpected archive fetch: {url}")
        return self.archives[url]
```

(e) Update `_build_service` to pass the trusted test key (the signature URL derives from the index URL automatically):

```python
def _build_service(
    plugins_dir: Path,
    core: CoreVersions,
    fake: _Fake,
    *,
    cache_ttl: int = 300,
) -> MarketplaceService:
    installer = PluginInstaller(
        plugins_dir=plugins_dir,
        core_versions=core,
        fetcher=fake.fetch_archive,
        pip_runner=lambda reqs, target, cv: target.mkdir(parents=True, exist_ok=True),
    )
    return MarketplaceService(
        index_url="https://plugins.example/index.json",
        installer=installer,
        index_fetcher=fake.fetch_index,
        public_keys=[_TEST_PUB_B64],
        cache_ttl=cache_ttl,
    )
```

(f) Append new tests at the end of the file:

```python
class TestSignatureGate:
    def test_rejects_invalid_signature(self, plugins_dir: Path, core: CoreVersions):
        idx = _make_index(
            [("demo", "1.0.0", _build_plugin_zip("demo"), "https://plugins.example/demo.bhplugin")]
        )
        fake = _Fake(index=idx, archives={}, signature=base64.b64encode(b"\x00" * 64))
        svc = _build_service(plugins_dir, core, fake)
        with pytest.raises(IndexSignatureError):
            svc.get_index()

    def test_rejects_unfetchable_signature(self, plugins_dir: Path, core: CoreVersions):
        idx = _make_index(
            [("demo", "1.0.0", _build_plugin_zip("demo"), "https://plugins.example/demo.bhplugin")]
        )
        fake = _Fake(index=idx, archives={}, sig_fetch_error=True)
        svc = _build_service(plugins_dir, core, fake)
        with pytest.raises(IndexSignatureError):
            svc.get_index()

    def test_valid_signature_returns_index(self, plugins_dir: Path, core: CoreVersions):
        idx = _make_index(
            [("demo", "1.0.0", _build_plugin_zip("demo"), "https://plugins.example/demo.bhplugin")]
        )
        fake = _Fake(index=idx, archives={})
        svc = _build_service(plugins_dir, core, fake)
        assert svc.get_index().get_plugin("demo").latest_version == "1.0.0"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `python -m pytest tests/plugins/test_plugin_marketplace_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'IndexSignatureError'` (and the new tests can't run). This proves the service change is needed.

- [ ] **Step 3: Implement the signature gate in the service**

In `backend/app/services/plugin_marketplace.py`:

(a) Add the import (after the existing `from app.plugins...` imports):

```python
from app.plugins.signing import SignatureError, verify_detached_ed25519
```

(b) Add the error class next to the other marketplace errors (after `IndexParseError`):

```python
class IndexSignatureError(MarketplaceError):
    """``index.json`` failed detached-signature verification (or the .sig
    could not be fetched). Fail-closed: the index is never trusted."""
```

(c) Extend `__init__` to accept and store the new params. Replace the signature and body of `__init__`:

```python
    def __init__(
        self,
        *,
        index_url: str,
        installer: PluginInstaller,
        public_keys: Sequence[str],
        signature_url: Optional[str] = None,
        index_fetcher: Optional[IndexFetcher] = None,
        cache_ttl: int = 300,
    ) -> None:
        self._index_url = index_url
        self._signature_url = signature_url or (index_url + ".sig")
        self._public_keys = list(public_keys)
        self._installer = installer
        self._fetch = index_fetcher or _default_index_fetcher
        self._cache_ttl = cache_ttl
        self._cache: Optional[CachedIndex] = None
```

(d) In `get_index()`, insert the signature gate immediately after the index-fetch `try/except` block and *before* `payload = json.loads(raw)`:

```python
        try:
            sig = self._fetch(self._signature_url)
        except Exception as exc:
            raise IndexSignatureError(
                f"failed to fetch index signature from {self._signature_url}: {exc}"
            ) from exc

        try:
            verify_detached_ed25519(raw, sig.decode("ascii").strip(), self._public_keys)
        except (SignatureError, UnicodeDecodeError) as exc:
            raise IndexSignatureError(f"index signature verification failed: {exc}") from exc
```

(`Sequence` is already imported in this file via `from typing import Callable, Optional, Sequence`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/plugins/test_plugin_marketplace_service.py -v`
Expected: PASS — all existing tests (now signed) plus the 3 new `TestSignatureGate` tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/plugin_marketplace.py backend/tests/plugins/test_plugin_marketplace_service.py
git commit -F <msgfile>   # subject: "feat(plugin-market): fail-closed index signature gate in MarketplaceService" + footer
```

---

### Task 3: Config settings + service wiring + route 502 mapping

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/plugin_marketplace.py` (`get_marketplace_service`)
- Modify: `backend/app/api/routes/plugins_marketplace.py`
- Modify (test): `backend/tests/api/test_plugins_marketplace_routes.py`

**Interfaces:**
- Consumes: the `MarketplaceService(public_keys=..., signature_url=...)` constructor from Task 2; `IndexSignatureError`.
- Produces: settings `plugins_marketplace_public_keys: list[str]` (default empty) and `plugins_marketplace_signature_url: str | None`.

- [ ] **Step 1: Update the route test helpers + add the failing 502 test**

In `backend/tests/api/test_plugins_marketplace_routes.py`:

(a) Add imports near the top:

```python
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
```

(b) Add a module-level test keypair (after imports, before `_build_plugin_zip`):

```python
_TEST_SK = Ed25519PrivateKey.generate()
_TEST_PUB_B64 = base64.b64encode(
    _TEST_SK.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode()
```

(c) Replace `_build_service` with a signed, URL-aware version that can optionally serve a bad signature:

```python
def _build_service(
    plugins_dir: Path,
    *,
    index: dict,
    archives: Dict[str, bytes],
    bad_signature: bool = False,
):
    core = CoreVersions(
        baluhost_version="1.30.0",
        python_version="3.11",
        platform="linux_x86_64",
        abi="cp311",
        packages={},
    )
    installer = PluginInstaller(
        plugins_dir=plugins_dir,
        core_versions=core,
        fetcher=lambda url: archives[url],
        pip_runner=lambda r, t, c: t.mkdir(parents=True, exist_ok=True),
    )
    index_url = "https://plugins.example/index.json"
    sig_url = index_url + ".sig"
    index_bytes = json.dumps(index).encode()
    signature = (
        base64.b64encode(b"\x00" * 64)
        if bad_signature
        else base64.b64encode(_TEST_SK.sign(index_bytes))
    )

    def _fetch(url: str) -> bytes:
        return signature if url == sig_url else index_bytes

    return MarketplaceService(
        index_url=index_url,
        installer=installer,
        index_fetcher=_fetch,
        public_keys=[_TEST_PUB_B64],
    )
```

(d) Update the `override_marketplace` fixture's `_attach` to pass `bad_signature` through:

```python
    def _attach(index: dict, archives: Dict[str, bytes], *, bad_signature: bool = False) -> MarketplaceService:
        service = _build_service(plugins_dir, index=index, archives=archives, bad_signature=bad_signature)
        created["svc"] = service
        app.dependency_overrides[get_marketplace_service] = lambda: service
        return service
```

(e) Add a test inside `class TestListMarketplace`:

```python
    def test_signature_failure_returns_scrubbed_502(
        self, client: TestClient, admin_headers: dict, override_marketplace
    ):
        _, attach = override_marketplace
        archive = _build_plugin_zip("demo")
        attach(
            _make_index([("demo", "1.0.0", archive, "https://plugins.example/demo.bhplugin")]),
            {},
            bad_signature=True,
        )
        response = client.get("/api/plugins/marketplace", headers=admin_headers)
        assert response.status_code == 502
        assert response.json()["detail"] == "marketplace index signature verification failed"
```

- [ ] **Step 2: Run the route tests to verify the new test fails**

Run (from `backend/`): `python -m pytest tests/api/test_plugins_marketplace_routes.py -v`
Expected: FAIL — the new test gets a 500 (unmapped `IndexSignatureError`) instead of a scrubbed 502; existing tests still pass (they now sign correctly).

- [ ] **Step 3: Add the config settings**

In `backend/app/core/config.py`, immediately after line 249 (`plugins_marketplace_cache_ttl: int = 300`) and before the `# Plugin sandbox (Track B, Phase 5a)` block, add:

```python
    # Marketplace index signing (Track C) — trusted ed25519 public keys, each
    # base64 of the 32-byte raw key. Empty default = fail-closed until a key is
    # provisioned (deploy/scripts/install-marketplace-pubkey.sh). Env (JSON,
    # single-quoted in .env.production): PLUGINS_MARKETPLACE_PUBLIC_KEYS='["<b64>"]'.
    plugins_marketplace_public_keys: list[str] = Field(default_factory=list)
    # Detached signature URL; None → derived as <index_url> + ".sig".
    plugins_marketplace_signature_url: str | None = None
```

(`Field` is already imported at the top of `config.py`.)

- [ ] **Step 4: Thread the settings into `get_marketplace_service()`**

In `backend/app/services/plugin_marketplace.py`, in `get_marketplace_service()`, update the `MarketplaceService(...)` construction (currently `index_url=..., installer=..., cache_ttl=...`) to also pass the keys + signature URL:

```python
    _instance = MarketplaceService(
        index_url=settings.plugins_marketplace_index_url,
        installer=installer,
        public_keys=settings.plugins_marketplace_public_keys,
        signature_url=settings.plugins_marketplace_signature_url,
        cache_ttl=settings.plugins_marketplace_cache_ttl,
    )
    return _instance
```

- [ ] **Step 5: Map `IndexSignatureError` → 502 in the routes**

In `backend/app/api/routes/plugins_marketplace.py`:

(a) Add `IndexSignatureError` to the `from app.services.plugin_marketplace import (...)` block.

(b) In `list_marketplace`, add a new `except` clause after the `IndexParseError` handler:

```python
    except IndexSignatureError as exc:
        logger.warning("marketplace index signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="marketplace index signature verification failed",
        ) from exc
```

(c) In `install_plugin`, the index lookup can also raise it (`install` → `get_version_entry` → `get_index`). Add, before the `except (DownloadError, IndexFetchError)` clause:

```python
    except IndexSignatureError as exc:
        logger.warning("marketplace index signature verification failed for %r: %s", plugin_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="marketplace index signature verification failed",
        ) from exc
```

- [ ] **Step 6: Run the route tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/api/test_plugins_marketplace_routes.py -v`
Expected: PASS (including the new scrubbed-502 test).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/services/plugin_marketplace.py backend/app/api/routes/plugins_marketplace.py backend/tests/api/test_plugins_marketplace_routes.py
git commit -F <msgfile>   # subject: "feat(plugin-market): config keys + route 502 mapping for index signing" + footer
```

---

### Task 4: Deploy smoke-check (entrypoint + ci-deploy.sh step)

**Files:**
- Create: `backend/app/plugins/verify_index_signature.py`
- Test: `backend/tests/plugins/test_verify_index_signature.py`
- Modify: `deploy/scripts/ci-deploy.sh`

**Interfaces:**
- Consumes: `verify_detached_ed25519` / `SignatureError` from Task 1; `settings` from Task 3.
- Produces: `check_index_signature(index_url, signature_url, public_keys, fetcher) -> tuple[bool, str]` (never raises) + a `python -m app.plugins.verify_index_signature` entrypoint that always exits 0.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_verify_index_signature.py`:

```python
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.plugins.verify_index_signature import check_index_signature

_SK = Ed25519PrivateKey.generate()
_PUB = base64.b64encode(
    _SK.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode()

_INDEX = b'{"index_version": 1, "plugins": []}'
_SIG = base64.b64encode(_SK.sign(_INDEX))
_IDX_URL = "https://m.example/index.json"
_SIG_URL = _IDX_URL + ".sig"


def _fetcher(mapping):
    def _f(url):
        return mapping[url]
    return _f


def test_valid_index_passes():
    ok, msg = check_index_signature(
        _IDX_URL, _SIG_URL, [_PUB], _fetcher({_IDX_URL: _INDEX, _SIG_URL: _SIG})
    )
    assert ok is True


def test_empty_key_warns_not_configured():
    ok, msg = check_index_signature(
        _IDX_URL, _SIG_URL, [], _fetcher({_IDX_URL: _INDEX, _SIG_URL: _SIG})
    )
    assert ok is False
    assert msg == "marketplace signing not configured"


def test_fetch_failure_warns():
    def boom(url):
        raise RuntimeError("network down")

    ok, msg = check_index_signature(_IDX_URL, _SIG_URL, [_PUB], boom)
    assert ok is False
    assert "could not fetch" in msg


def test_invalid_signature_warns():
    bad = base64.b64encode(b"\x00" * 64)
    ok, msg = check_index_signature(
        _IDX_URL, _SIG_URL, [_PUB], _fetcher({_IDX_URL: _INDEX, _SIG_URL: bad})
    )
    assert ok is False
    assert "verification failed" in msg


def test_never_raises_on_garbage():
    # A fetcher returning non-bytes / nonsense must not crash the check.
    ok, msg = check_index_signature(_IDX_URL, _SIG_URL, [_PUB], lambda url: 12345)
    assert ok is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`): `python -m pytest tests/plugins/test_verify_index_signature.py -v`
Expected: FAIL — `ModuleNotFoundError: app.plugins.verify_index_signature`.

- [ ] **Step 3: Write the entrypoint module**

Create `backend/app/plugins/verify_index_signature.py`:

```python
"""Deploy smoke-check: verify the live marketplace index signature.

Run as ``python -m app.plugins.verify_index_signature``. ALWAYS exits 0 — a
signing hiccup must never fail a deploy. Prints ``PASS: <msg>`` or
``WARN: <reason>`` for the deploy log. Reuses ``verify_detached_ed25519``.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional, Sequence

from app.plugins.signing import SignatureError, verify_detached_ed25519


def check_index_signature(
    index_url: str,
    signature_url: str,
    public_keys: Sequence[str],
    fetcher: Callable[[str], bytes],
) -> tuple[bool, str]:
    """Return ``(ok, message)``. Never raises."""
    if not list(public_keys):
        return False, "marketplace signing not configured"
    try:
        raw = fetcher(index_url)
        sig = fetcher(signature_url)
        sig_b64 = sig.decode("ascii").strip()
    except Exception as exc:  # noqa: BLE001 - smoke-check must not crash
        return False, f"could not fetch index or signature: {exc}"
    try:
        verify_detached_ed25519(raw, sig_b64, public_keys)
    except (SignatureError, UnicodeDecodeError) as exc:
        return False, f"signature verification failed: {exc}"
    except Exception as exc:  # noqa: BLE001 - defensive: never crash the deploy
        return False, f"unexpected verification error: {exc}"
    return True, "signature OK"


def _default_fetcher(url: str) -> bytes:
    import httpx

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def main(argv: Optional[Sequence[str]] = None) -> int:
    from app.core.config import settings

    index_url = settings.plugins_marketplace_index_url
    sig_url = settings.plugins_marketplace_signature_url or (index_url + ".sig")
    ok, message = check_index_signature(
        index_url, sig_url, settings.plugins_marketplace_public_keys, _default_fetcher
    )
    print(f"PASS: {message}" if ok else f"WARN: {message}")
    return 0  # always non-fatal


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `backend/`): `python -m pytest tests/plugins/test_verify_index_signature.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire the non-fatal step into `ci-deploy.sh`**

In `deploy/scripts/ci-deploy.sh`, inside the success branch of the final `if health_check; then` block, after the `log_info "Backup: $BACKUP_FILE"` line and before the companion `if [[ "${INSTALL_COMPANION:-0}" ...` block, insert:

```bash
    # ─── 8b. Marketplace Signature Smoke-Check (non-fatal) ───────────────
    # Verify the live marketplace index is signed by a configured trusted key.
    # Never fails the deploy: the backend already fail-closes the (admin-only)
    # Marketplace listing, so a signing hiccup has no runtime-plugin impact.
    # The entrypoint always exits 0 and prints PASS/WARN; the `|| log_warn`
    # only catches a failure to launch python at all.
    log_step "Marketplace Signature Smoke-Check"
    ( cd "$INSTALL_DIR/backend" && "$VENV_BIN/python" -m app.plugins.verify_index_signature ) \
        || log_warn "Marketplace smoke-check could not run (non-fatal)."
```

- [ ] **Step 6: Syntax-check the deploy script**

Run: `bash -n deploy/scripts/ci-deploy.sh`
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/app/plugins/verify_index_signature.py backend/tests/plugins/test_verify_index_signature.py deploy/scripts/ci-deploy.sh
git commit -F <msgfile>   # subject: "feat(plugin-market): per-deploy marketplace signature smoke-check" + footer
```

---

### Task 5: Provisioning helper `install-marketplace-pubkey.sh`

**Files:**
- Create: `deploy/scripts/install-marketplace-pubkey.sh`

**Interfaces:**
- Consumes: a server-side key file (default `/etc/baluhost/marketplace-pubkey.b64`).
- Produces: an idempotent `PLUGINS_MARKETPLACE_PUBLIC_KEYS='[...]'` line in `/opt/baluhost/.env.production`.

- [ ] **Step 1: Write the helper script**

Create `deploy/scripts/install-marketplace-pubkey.sh`:

```bash
#!/bin/bash
# Idempotently set PLUGINS_MARKETPLACE_PUBLIC_KEYS in .env.production from a
# server-side base64 public-key file (one key per line, '#' comments allowed).
# Public material only — no secret handling. Run as root at setup / on key
# rotation. Validates each key is base64 of exactly 32 bytes before writing,
# so a bad key never silently fail-closes the marketplace.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/baluhost}"
ENV_FILE="$INSTALL_DIR/.env.production"
PUBKEY_FILE="${MARKETPLACE_PUBKEY_FILE:-/etc/baluhost/marketplace-pubkey.b64}"
KEY_VAR="PLUGINS_MARKETPLACE_PUBLIC_KEYS"

err() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]]    || err "$ENV_FILE not found"
[[ -f "$PUBKEY_FILE" ]] || err "public key file $PUBKEY_FILE not found"

# Collect non-empty, non-comment keys; validate each decodes to 32 bytes.
keys=()
while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"   # ltrim
    line="${line%"${line##*[![:space:]]}"}"     # rtrim
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    nbytes=$(printf '%s' "$line" | base64 -d 2>/dev/null | wc -c) \
        || err "key is not valid base64: $line"
    [[ "$nbytes" -eq 32 ]] \
        || err "key is not a 32-byte ed25519 public key (got $nbytes bytes): $line"
    keys+=("$line")
done < "$PUBKEY_FILE"

[[ "${#keys[@]}" -gt 0 ]] || err "no public keys found in $PUBKEY_FILE"

# Build JSON array: ["k1","k2"]
json="["
for i in "${!keys[@]}"; do
    [[ "$i" -gt 0 ]] && json+=","
    json+="\"${keys[$i]}\""
done
json+="]"

# Single-quote the value: bash `source` (ci-deploy), systemd EnvironmentFile,
# and python-dotenv each strip one outer quote layer and keep the inner JSON
# quotes intact. An unquoted value loses its inner quotes under bash `source`.
new_line="$KEY_VAR='$json'"

# Idempotent set: no-op if identical, replace if present, append if absent.
# Write through the existing file (truncate+rewrite) to preserve owner/mode.
if existing=$(sed -n "s/^${KEY_VAR}=.*/&/p" "$ENV_FILE") && [[ -n "$existing" ]]; then
    if [[ "$existing" == "$new_line" ]]; then
        echo "$KEY_VAR already up to date in $ENV_FILE"
        exit 0
    fi
    tmp=$(mktemp)
    sed "/^${KEY_VAR}=/d" "$ENV_FILE" > "$tmp"
    printf '%s\n' "$new_line" >> "$tmp"
    cat "$tmp" > "$ENV_FILE"
    rm -f "$tmp"
    echo "Updated $KEY_VAR in $ENV_FILE"
else
    printf '%s\n' "$new_line" >> "$ENV_FILE"
    echo "Appended $KEY_VAR to $ENV_FILE"
fi
```

- [ ] **Step 2: Syntax-check the script**

Run: `bash -n deploy/scripts/install-marketplace-pubkey.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Idempotency smoke-test on temp fixtures**

Generate a real test key, run the helper against temp files, and confirm the env line is correct and idempotent. Run from the repo root (no `grep`/`rg` in this command):

```bash
TMP=$(mktemp -d)
PUB=$(python -c "import base64;from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as K;from cryptography.hazmat.primitives import serialization as s;print(base64.b64encode(K.generate().public_key().public_bytes(s.Encoding.Raw,s.PublicFormat.Raw)).decode())")
printf 'DATABASE_URL=postgresql://x\n' > "$TMP/.env.production"
printf '# comment\n%s\n' "$PUB" > "$TMP/key.b64"
INSTALL_DIR="$TMP" MARKETPLACE_PUBKEY_FILE="$TMP/key.b64" bash deploy/scripts/install-marketplace-pubkey.sh
INSTALL_DIR="$TMP" MARKETPLACE_PUBKEY_FILE="$TMP/key.b64" bash deploy/scripts/install-marketplace-pubkey.sh
cat "$TMP/.env.production"
```

Expected: first run prints `Appended PLUGINS_MARKETPLACE_PUBLIC_KEYS …`, second prints `… already up to date`, and the final `cat` shows the original `DATABASE_URL` line plus exactly one line `PLUGINS_MARKETPLACE_PUBLIC_KEYS='["<PUB>"]'` (single-quoted, inner double quotes intact).

- [ ] **Step 4: Verify the written value round-trips as JSON**

Run (confirms the inner quotes survive and parse):

```bash
python -c "import json,re,io; s=open('$TMP/.env.production').read(); line=[l for l in s.splitlines() if l.startswith('PLUGINS_MARKETPLACE_PUBLIC_KEYS=')][0]; val=line.split('=',1)[1].strip().strip(chr(39)); print('parsed:', json.loads(val))"
```

Expected: `parsed: ['<PUB>']` — a one-element list, proving the JSON survived the single-quote wrapping.

- [ ] **Step 5: Commit**

```bash
git add deploy/scripts/install-marketplace-pubkey.sh
git commit -F <msgfile>   # subject: "feat(plugin-market): idempotent marketplace public-key provisioning helper" + footer
```

---

## Self-Review

**1. Spec coverage:**
- Detached raw-ed25519 verify util → Task 1. ✓
- Fail-closed gate in `get_index()` before parse; `IndexSignatureError` → Task 2. ✓
- Cache re-verifies (gate is inside the fetch-on-miss path; cached path returns early) → Task 2 Step 3. ✓
- Config `plugins_marketplace_public_keys` (empty default) + `plugins_marketplace_signature_url` → Task 3 Step 3. ✓
- `get_marketplace_service()` threading → Task 3 Step 4. ✓
- Route 502 scrubbed mapping (list + install) → Task 3 Step 5. ✓
- Per-deploy non-fatal smoke-check (entrypoint + ci-deploy.sh) → Task 4. ✓
- One-time idempotent provisioning helper → Task 5. ✓
- Rotation (list of keys), fork (env override), companion-repo checklist → covered by the empty-default + list config (Task 3) and remain operator steps in the spec; no code beyond the list. ✓
- Tests: signing unit, service gate, route 502, smoke-check, helper idempotency → Tasks 1–5. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every run step has an exact command + expected result. `<msgfile>` denotes "write the message (subject line shown + the two-line footer) and commit with `git commit -F`" — per Global Constraints, not a content placeholder.

**3. Type/name consistency:** `verify_detached_ed25519(message, signature_b64, public_keys_b64)` and `SignatureError` identical across Tasks 1/2/4. `IndexSignatureError` defined in Task 2, imported in Task 3. `MarketplaceService.__init__` keyword params `public_keys` + `signature_url` match the calls in Task 2 test helpers, Task 3 `get_marketplace_service`, and Task 3 route test helper. `check_index_signature(index_url, signature_url, public_keys, fetcher) -> tuple[bool, str]` consistent between Task 4 module and test. Config field names match the settings reads in `get_marketplace_service` (Task 3) and the smoke-check `main()` (Task 4). Env var `PLUGINS_MARKETPLACE_PUBLIC_KEYS` single-quoted form consistent between the helper (Task 5) and the Global Constraints rationale.

**4. Critical-path checks:** Existing marketplace tests would break without the URL-aware signed fakes — addressed in Task 2 Step 1 (service tests) and Task 3 Step 1 (route tests), which are done *before* the corresponding source change so the failing run is observed. The `.sig` fetch reuses the single injected fetcher — both fakes branch on the sig URL. Install route raises `IndexSignatureError` via `get_index` — mapped in Task 3 Step 5(c).

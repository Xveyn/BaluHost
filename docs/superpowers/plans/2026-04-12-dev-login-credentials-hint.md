# Dynamic Dev-Mode Login Credentials Hint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `admin / changeme` hint on the Login page with the real admin credentials from `settings`, exposed via the existing `GET /api/system/mode` endpoint — dev mode only.

**Architecture:** The existing public `/api/system/mode` endpoint is extended to include a `dev_credentials` object (`{username, password}`) when `settings.is_dev_mode` is true. The React Login page consumes this field and renders it in the existing hint block. In production, the field is absent from the response and the hint block is not rendered.

**Tech Stack:** FastAPI, Pydantic, pytest (backend); React 18 + TypeScript + Vite (frontend).

**Spec:** `docs/superpowers/specs/2026-04-12-dev-login-credentials-hint-design.md`

---

## File Structure

**Backend:**
- Modify: `backend/app/api/routes/system.py` — `get_system_mode` handler
- Modify: `backend/tests/test_dev_mode.py` — two new tests (dev, prod)

**Frontend:**
- Modify: `client/src/pages/Login.tsx` — state + effect + hint block
- Modify: `client/src/api/system.ts` — widen `getSystemMode` return type

No new files.

---

## Task 1: Backend — Extend `get_system_mode` with dev credentials

**Files:**
- Modify: `backend/app/api/routes/system.py` (lines 32-37)
- Test: `backend/tests/test_dev_mode.py`

- [ ] **Step 1: Write the failing test for dev mode**

Open `backend/tests/test_dev_mode.py` and append this test at the end of the file:

```python
def test_system_mode_returns_dev_credentials(client: TestClient) -> None:
    """In dev mode, /api/system/mode must include the admin credentials."""
    response = client.get(f"{settings.api_prefix}/system/mode")
    assert response.status_code == 200
    data = response.json()
    assert data["dev_mode"] is True
    assert "dev_credentials" in data
    assert data["dev_credentials"]["username"] == settings.admin_username
    assert data["dev_credentials"]["password"] == settings.admin_password
```

- [ ] **Step 2: Write the failing test for prod mode**

Append this test directly after the previous one:

```python
def test_system_mode_prod_omits_credentials(client: TestClient) -> None:
    """In prod mode, /api/system/mode must NOT leak credentials."""
    from unittest.mock import patch

    # The handler imports `settings` inside the function body via
    # `from app.core.config import settings`, so patching the module
    # attribute replaces what the handler sees on the next request.
    # See backend/tests/test_fritzbox_wol.py:51-56 for the same pattern.
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.is_dev_mode = False
        response = client.get(f"{settings.api_prefix}/system/mode")

    assert response.status_code == 200
    data = response.json()
    assert data["dev_mode"] is False
    assert "dev_credentials" not in data
```

Note: the outer `settings.api_prefix` call uses the real (unpatched) settings to build the URL — only the handler's internal `settings` lookup is mocked. The rate limiter (`@limiter.limit(get_limit("system_monitor"))`) uses its own decorator-time lookup and is unaffected.

- [ ] **Step 3: Run both tests to verify they fail**

Run from `backend/`:
```bash
python -m pytest tests/test_dev_mode.py::test_system_mode_returns_dev_credentials tests/test_dev_mode.py::test_system_mode_prod_omits_credentials -v
```

Expected: Both FAIL — the dev test fails on `assert "dev_credentials" in data` because the current handler only returns `{"dev_mode": ...}`.

- [ ] **Step 4: Implement the handler change**

Open `backend/app/api/routes/system.py` and replace the existing `get_system_mode` function (around lines 32-37):

```python
@router.get("/mode")
@limiter.limit(get_limit("system_monitor"))
async def get_system_mode(request: Request, response: Response) -> dict:
    """Get system mode (dev/prod). Public endpoint for login page.

    In dev mode, includes the seeded admin credentials so the Login page
    can display an accurate default-credentials hint. In prod mode the
    credentials field is omitted entirely.
    """
    from app.core.config import settings
    payload: dict = {"dev_mode": settings.is_dev_mode}
    if settings.is_dev_mode:
        payload["dev_credentials"] = {
            "username": settings.admin_username,
            "password": settings.admin_password,
        }
    return payload
```

- [ ] **Step 5: Run both tests to verify they pass**

Run:
```bash
python -m pytest tests/test_dev_mode.py::test_system_mode_returns_dev_credentials tests/test_dev_mode.py::test_system_mode_prod_omits_credentials -v
```

Expected: Both PASS.

- [ ] **Step 6: Run the full `test_dev_mode.py` suite to make sure nothing else broke**

Run:
```bash
python -m pytest tests/test_dev_mode.py -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/system.py backend/tests/test_dev_mode.py
git commit -m "feat(system): expose admin credentials via /api/system/mode in dev"
```

---

## Task 2: Frontend — Widen `getSystemMode` return type

**Files:**
- Modify: `client/src/api/system.ts` (lines 57-60)

This is a pure type change so no test is added; TypeScript compilation is the verification.

- [ ] **Step 1: Update the type**

Open `client/src/api/system.ts` and replace the `getSystemMode` function (around lines 57-60):

```typescript
export async function getSystemMode(): Promise<{
  dev_mode: boolean;
  dev_credentials?: { username: string; password: string };
}> {
  const { data } = await apiClient.get<{
    dev_mode: boolean;
    dev_credentials?: { username: string; password: string };
  }>('/api/system/mode');
  return data;
}
```

- [ ] **Step 2: Run typecheck**

From `client/`:
```bash
npm run build
```

Or if a faster typecheck script exists:
```bash
npx tsc --noEmit
```

Expected: Build/typecheck PASSES with no errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/api/system.ts
git commit -m "refactor(api): widen getSystemMode type with dev_credentials"
```

---

## Task 3: Frontend — Render dynamic credentials on Login page

**Files:**
- Modify: `client/src/pages/Login.tsx` (lines 21, 40-46, 322-326)

- [ ] **Step 1: Replace the `isDevMode` state with `devCredentials`**

Open `client/src/pages/Login.tsx`. Find line 21:

```tsx
  const [isDevMode, setIsDevMode] = useState(false);
```

Replace with:

```tsx
  const [devCredentials, setDevCredentials] = useState<
    { username: string; password: string } | null
  >(null);
```

- [ ] **Step 2: Update the effect that fetches the mode**

Find the effect at lines 40-46:

```tsx
  // Check if running in dev mode (for showing default credentials)
  useEffect(() => {
    fetch('/api/system/mode')
      .then(res => res.json())
      .then(data => setIsDevMode(data.dev_mode === true))
      .catch(() => setIsDevMode(false));
  }, []);
```

Replace with:

```tsx
  // Check if running in dev mode (for showing default credentials)
  useEffect(() => {
    fetch('/api/system/mode')
      .then(res => res.json())
      .then(data => {
        if (data.dev_mode === true && data.dev_credentials) {
          setDevCredentials({
            username: String(data.dev_credentials.username ?? ''),
            password: String(data.dev_credentials.password ?? ''),
          });
        } else {
          setDevCredentials(null);
        }
      })
      .catch(() => setDevCredentials(null));
  }, []);
```

- [ ] **Step 3: Update the hint block**

Find the block at lines 322-326:

```tsx
              {isDevMode && (
                <div className="mt-6 sm:mt-8 rounded-xl border border-slate-800 bg-slate-950-secondary p-3 sm:p-4 text-center text-xs text-slate-100-tertiary">
                  {t('defaultCredentials')} - <span className="text-slate-100-secondary">admin</span> / <span className="text-slate-100-secondary">changeme</span>
                </div>
              )}
```

Replace with:

```tsx
              {devCredentials && (
                <div className="mt-6 sm:mt-8 rounded-xl border border-slate-800 bg-slate-950-secondary p-3 sm:p-4 text-center text-xs text-slate-100-tertiary">
                  {t('defaultCredentials')} - <span className="text-slate-100-secondary">{devCredentials.username}</span> / <span className="text-slate-100-secondary">{devCredentials.password}</span>
                </div>
              )}
```

- [ ] **Step 4: Run typecheck / build to make sure the file still compiles**

From `client/`:
```bash
npm run build
```

Expected: PASS with no errors.

- [ ] **Step 5: Manual smoke test**

Start the dev server (from repo root):
```bash
python start_dev.py
```

Open `http://localhost:5173/login` in a browser and verify:
- The hint block at the bottom of the login card reads `Default credentials - admin / DevMode2024` (or whatever `ADMIN_PASSWORD` you have set in your env).
- Logging in with those credentials succeeds.
- The 2FA flow (if enabled) is not affected.

Stop the dev server (Ctrl+C) once verified.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/Login.tsx
git commit -m "feat(login): show dynamic admin credentials in dev hint"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run full backend test suite**

From `backend/`:
```bash
python -m pytest -q
```

Expected: All tests PASS. If anything unrelated fails, stop and investigate before proceeding.

- [ ] **Step 2: Run frontend build**

From `client/`:
```bash
npm run build
```

Expected: PASS.

- [ ] **Step 3: Verify all commits are on the branch**

```bash
git log --oneline -5
```

Expected: Three new commits on top of the spec commit, in this order:
1. `feat(system): expose admin credentials via /api/system/mode in dev`
2. `refactor(api): widen getSystemMode type with dev_credentials`
3. `feat(login): show dynamic admin credentials in dev hint`

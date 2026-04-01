# Setup Wizard Design

**Date:** 2026-04-01
**Status:** Approved
**Scope:** Full onboarding wizard for first-time BaluHost setup

## Problem

BaluHost has no setup process after initial installation. The admin account is created from environment variables, and all configuration (RAID, file access, features) must be done manually after login. This is developer-centric and not suitable for a NAS product.

## Solution

A browser-based setup wizard that appears on first start (no users in DB). Guides the user through 4 required steps and up to 7 optional feature steps. Can be skipped entirely via `BALUHOST_SKIP_SETUP=true` for automated deployments.

## Wizard Flow

```
[Start] → Step 1: Admin Account
        → Step 2: Create Users (min. 1)
        → Step 3: RAID Configuration
        → Step 4: File Access (Samba/WebDAV)
        → [Optional Gate]
            → "Alle überspringen & loslegen" → [Summary] → [Dashboard]
            → "Features durchgehen" →
                Step 5: Sharing (skip?)
                Step 6: VPN/WireGuard (skip?)
                Step 7: Notifications/Firebase (skip?)
                Step 8: Cloud Import/rclone (skip?)
                Step 9: Pi-hole (skip?)
                Step 10: Desktop Sync (skip?)
                Step 11: Mobile App (skip?)
                → [Summary] → [Dashboard]
```

## Trigger Logic

- Backend checks if the `users` table is empty on startup
- `GET /api/setup/status` returns `{ setup_required: bool, completed_steps: string[] }`
- Frontend checks setup status after backend-ready, redirects to `/setup` if required
- `BALUHOST_SKIP_SETUP=true` → status always returns `{ setup_required: false }`, admin creation falls back to env vars (`ensure_admin_user()` as today)

## State & Persistence

No persisted wizard state. On reload or reconnect, `/api/setup/status` detects which required steps are already completed by checking live state:

| Check | Condition | Step |
|-------|-----------|------|
| Admin exists? | User with `role=admin` in DB | Step 1 |
| Regular user exists? | User with `role=user` in DB | Step 2 |
| RAID array exists? | At least one array in RAID status | Step 3 |
| File access active? | Samba and/or WebDAV service enabled | Step 4 |

Wizard jumps to the first incomplete required step. Already-created entities (admin, users) persist across reloads.

## Required Steps

### Step 1: Admin Account

Creates the system administrator account.

**UI:**
- Username, Password (with strength indicator), E-Mail (optional)
- Hint text: "Dieser Account dient zur Systemverwaltung und Konfiguration."
- Password validation: same rules as `RegisterRequest` (8-128 chars, upper+lower+digit, blacklist)

**Endpoint:** `POST /api/setup/admin`
- Request: `{ username, password, email?, setup_secret? }`
- Response: `{ success: bool, setup_token: string }` — JWT with `type: "setup"`, short TTL (30 min)
- No auth required (protected by guards, see Security section)

### Step 2: Create Users

Creates regular NAS users. Admin role is for settings access, regular users are the actual NAS users.

**UI:**
- Form: Username, Password, E-Mail (optional)
- "+ Weiteren User hinzufügen" button to add more
- List of created users with delete option
- "Weiter" button disabled until at least 1 user exists

**Endpoint:** `POST /api/setup/users`
- Request: `{ username, password, email? }`
- Response: `{ success: bool, user: { id, username, email } }`
- Auth: Setup-Token

**Endpoint:** `DELETE /api/setup/users/{id}`
- Auth: Setup-Token
- Only allows deleting users created during setup (not the admin)

### Step 3: RAID Configuration

Full RAID wizard embedded from the existing SystemControlPage implementation.

**UI:**
- The existing RAID wizard component is extracted into a shared component (`RaidWizardCore`) used by both SystemControlPage and the setup wizard
- Full functionality: disk detection, RAID level selection, disk assignment, spare configuration
- No simplification — users setting up a NAS want full control over storage

**Endpoints:** Uses existing `/api/system/raid/*` endpoints
- Setup-Token grants admin-equivalent access to these endpoints

### Step 4: File Access (Samba / WebDAV)

At least one file access protocol must be activated for the NAS to be usable as a network drive.

**UI:**
- Two cards side by side: Samba and WebDAV
- Checkbox/toggle to activate each, at least one required
- On activation, a config panel expands:
  - **Samba:** Workgroup name (default: "WORKGROUP"), public browsing yes/no
  - **WebDAV:** Port (default: 8443), SSL yes/no
- "Weiter" button disabled until at least one is activated

**Endpoint:** `POST /api/setup/file-access`
- Request: `{ samba?: { enabled, workgroup, public_browsing }, webdav?: { enabled, port, ssl } }`
- Response: `{ success: bool, active_services: string[] }`
- Auth: Setup-Token

## Optional Gate

After Step 4, a decision screen:

- Headline: "Grundkonfiguration abgeschlossen!"
- Subtext: "Du kannst jetzt optionale Features einrichten oder direkt loslegen."
- **Primary button:** "Alle überspringen & loslegen" → calls `POST /api/setup/complete` → Dashboard
- **Secondary button:** "Features durchgehen" → continues to Step 5

## Optional Steps

Each step has a "Überspringen" button alongside the "Weiter" button. Each step configures one feature using existing backend endpoints where possible.

### Step 5: Sharing
- Enable public/user shares
- Quick-create a first share for a user's home directory

### Step 6: VPN (WireGuard)
- Enable VPN server
- Generate first client config
- Show QR code for mobile import

### Step 7: Notifications (Firebase)
- Upload or paste Firebase credentials JSON
- Send test notification
- Configure which events trigger notifications

### Step 8: Cloud Import (rclone)
- Add first rclone remote (Google Drive, Dropbox, etc.)
- Test connection

### Step 9: Pi-hole
- Enable Pi-hole integration
- Configure DNS settings

### Step 10: Desktop Sync
- Show BaluDesk download link
- Display pairing information/instructions

### Step 11: Mobile App
- Show BaluApp download link
- Generate QR code for app pairing (includes VPN config if enabled in Step 6)

## Summary Screen

Final screen after completing or skipping all steps:

- List of all features with status icons:
  - Checkmark (green): configured
  - Skip icon (gray): skipped
  - Dash (neutral): not applicable
- "Zum Dashboard" button → calls `POST /api/setup/complete` → redirects to Dashboard

## Backend Architecture

### New Files

```
backend/app/services/setup/
├── __init__.py
└── service.py          # is_setup_required(), complete_setup()

backend/app/api/routes/setup.py   # All /api/setup/* endpoints
backend/app/schemas/setup.py      # Request/response models
```

### Setup Service (`services/setup/service.py`)

```python
def is_setup_required() -> bool:
    """Check if setup wizard should be shown. Returns False if SKIP_SETUP or users exist."""

def get_completed_steps(db: Session) -> list[str]:
    """Check live state to determine which required steps are done."""

def complete_setup(db: Session) -> None:
    """Mark setup as complete. Sets internal flag to prevent re-triggering."""
```

### Setup Token

- JWT with `type: "setup"`, TTL 30 minutes
- Created after admin account is set up (Step 1 response)
- Accepted by setup endpoints and existing admin-only endpoints (RAID, Samba, WebDAV) during setup
- Implementation: new token type in `core/security.py`, new dependency `get_setup_or_admin_user` in `api/deps.py` that accepts either a setup token or a normal admin token

### Route Registration

- Registered in `app/main.py` alongside other routes
- All endpoints (except `/api/setup/status` and `/api/setup/admin`) require setup token
- Guard middleware/dependency: if `not is_setup_required()`, return 403 for all setup endpoints

### Env Vars

| Var | Default | Purpose |
|-----|---------|---------|
| `BALUHOST_SKIP_SETUP` | `false` | Skip wizard, use env-var admin creation |
| `BALUHOST_SETUP_SECRET` | (empty) | If set, must be provided in admin creation request |

Both added to `core/config.py` as `Settings` fields.

## Frontend Architecture

### New Files

```
client/src/pages/SetupWizard.tsx              # Main wizard page, step management
client/src/components/setup/
├── SetupProgress.tsx                          # Progress bar with step labels
├── AdminSetup.tsx                             # Step 1
├── UserSetup.tsx                              # Step 2
├── RaidSetup.tsx                              # Step 3 (embeds shared RAID component)
├── FileAccessSetup.tsx                        # Step 4
├── OptionalGate.tsx                           # Decision screen
├── SharingSetup.tsx                           # Step 5
├── VpnSetup.tsx                               # Step 6
├── NotificationSetup.tsx                      # Step 7
├── CloudImportSetup.tsx                       # Step 8
├── PiholeSetup.tsx                            # Step 9
├── DesktopSyncSetup.tsx                       # Step 10
├── MobileAppSetup.tsx                         # Step 11
└── SetupComplete.tsx                          # Summary screen
```

### Refactored Files

- **RAID Wizard extraction:** The RAID wizard core logic is extracted from `SystemControlPage` (or its sub-components) into a shared `RaidWizardCore` component. Both `SystemControlPage` and `RaidSetup.tsx` use this component.

### Routing Changes (`App.tsx`)

```tsx
// After backend ready, before AuthProvider:
// GET /api/setup/status → if setup_required, show SetupWizard

// New route (outside AuthProvider, no auth needed):
<Route path="/setup" element={<SetupWizard />} />

// Redirect logic:
// setup_required && path !== "/setup" → Navigate to /setup
// !setup_required && path === "/setup" → Navigate to /login
```

### SetupWizard.tsx State

```tsx
// Local React state only, no persistence
const [currentStep, setCurrentStep] = useState(0);
const [setupToken, setSetupToken] = useState<string | null>(null);
const [skippedOptionals, setSkippedOptionals] = useState(false);
```

- On mount: fetch `/api/setup/status`, determine first incomplete required step
- After Step 1: store setup token in state for subsequent requests
- Navigation: back allowed to completed steps, forward only after step completion

### Visual Design

- Fullscreen layout (no sidebar/Layout wrapper), consistent with Login screen styling
- BaluHost branding (logo + name) at top
- Progress bar below branding showing all steps (required steps marked differently from optional)
- Card-based step content in center
- Navigation buttons at bottom: "Zurück" (if applicable) | "Überspringen" (optional steps only) | "Weiter"

## Security

### `/api/setup/admin` Protection (4 layers)

1. **Primary guard:** 403 if any user exists in DB (endpoint is dead after first admin creation)
2. **Setup secret:** If `BALUHOST_SETUP_SECRET` env var is set, request must include matching `setup_secret` field. If not set, endpoint is open (guarded by layers 1, 3, 4)
3. **Local-network-only:** Uses existing `local_only` middleware — setup only from local network. Exception: if `BALUHOST_SETUP_SECRET` is set, remote access is allowed (secret provides the protection)
4. **Rate limiting:** Aggressive limit (3 requests/minute) via `@limiter.limit()`

### All Other Setup Endpoints

- Require valid setup token (JWT `type: "setup"`)
- 403 if `is_setup_required()` returns false
- Standard rate limiting

### Setup Token Security

- Short TTL (30 minutes) — enough for setup, auto-expires
- `type: "setup"` claim prevents use as regular access token
- Only created by `/api/setup/admin` endpoint
- After `POST /api/setup/complete`, setup tokens are effectively useless (all setup endpoints return 403)

## Testing Strategy

### Backend Tests (`backend/tests/setup/`)

#### Unit Tests (`test_setup_service.py`)
- `is_setup_required()` returns `true` when no users exist
- `is_setup_required()` returns `false` when users exist
- `is_setup_required()` returns `false` when `SKIP_SETUP=true`
- `get_completed_steps()` correctly detects each step's completion state
- `complete_setup()` sets the completion flag

#### Integration Tests (`test_setup_routes.py`)

**Status endpoint:**
- Returns `setup_required: true` on empty DB
- Returns `setup_required: false` after setup complete
- Returns `setup_required: false` when `SKIP_SETUP=true`
- Returns correct `completed_steps` list

**Admin creation:**
- Creates admin successfully with valid data
- Returns setup token on success
- Rejects weak passwords (same validation as RegisterRequest)
- Returns 403 if users already exist (guard)
- Returns 403 if setup secret is wrong (when configured)
- Rate limiting works (4th request within 1 min returns 429)

**User creation:**
- Creates user with valid setup token
- Rejects request without setup token (401)
- Rejects request with expired setup token
- Rejects request with regular access token (wrong type)
- Can create multiple users
- Can delete setup-created users
- Cannot delete admin user

**File access:**
- Activates Samba with config
- Activates WebDAV with config
- Activates both simultaneously
- Rejects request with neither enabled

**Complete:**
- Marks setup as complete
- After completion, all setup endpoints return 403
- After completion, `/api/setup/status` returns `setup_required: false`

#### Security Tests (`test_setup_security.py`)
- Setup endpoints inaccessible after setup is complete
- Setup token cannot be used as access token on regular endpoints
- Regular access token cannot be used on setup endpoints
- Admin endpoint only accessible from local network (when no setup secret)
- Admin endpoint accessible remotely with correct setup secret
- Admin endpoint rejects remote access with wrong setup secret

### Frontend Tests

#### Component Tests (Vitest)
- `SetupProgress` renders correct step count and highlights current step
- `AdminSetup` validates password strength before enabling submit
- `UserSetup` disables "Weiter" with 0 users, enables with 1+
- `FileAccessSetup` disables "Weiter" with neither service selected
- `OptionalGate` renders both action buttons
- `SetupComplete` shows correct status icons for configured/skipped features

#### E2E Tests (Playwright)
- Full happy path: Admin → User → RAID → File Access → Skip optionals → Dashboard
- Full happy path with optional features
- Reload mid-setup: resumes at correct step
- Setup not accessible after completion (redirect to login)
- Back navigation works between steps

## Migration Notes

- Existing deployments (with users in DB) are unaffected — wizard never triggers
- `BALUHOST_SKIP_SETUP` should be set in existing CI/CD pipelines and production `.env` files
- `ensure_admin_user()` remains functional when `SKIP_SETUP=true` — zero breaking changes for automated deployments
- New env vars added to `.env.example` with documentation

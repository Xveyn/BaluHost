# Plan: System Variables Page

## Context

Neuer Tab "System Variables" unter System Control → System, mit dem Admins die `.env`-Dateien (Backend + Client) direkt aus der UI bearbeiten koennen. Kuratierte Variablen gruppiert nach Kategorien mit passenden Input-Typen. Sensitive Werte maskiert mit Reveal-Toggle. Warnung im Header, da direkte Datei-Bearbeitung. Restart-Warnung nach Speichern.

---

## Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `backend/app/services/env_config.py` | Service: .env parsing, writing, variable registry |
| 2 | `backend/app/schemas/env_config.py` | Pydantic schemas (request/response) |
| 3 | `backend/app/api/routes/env_config.py` | API endpoints (GET, PUT, GET reveal) |
| 4 | `client/src/api/env-config.ts` | Frontend API client |
| 5 | `client/src/components/env-config/SystemVariablesTab.tsx` | Main UI component |
| 6 | `client/src/components/env-config/index.ts` | Barrel export |

## Files to Modify

| # | File | Change |
|---|------|--------|
| 7 | `backend/app/api/routes/__init__.py` | Register env_config router |
| 8 | `client/src/pages/SystemControlPage.tsx` | Add `envconfig` tab to System category |
| 9 | `client/src/i18n/locales/en/common.json` | Add `systemControl.tabs.envConfig` |
| 10 | `client/src/i18n/locales/de/common.json` | Add `systemControl.tabs.envConfig` |
| 11 | `client/src/i18n/locales/en/system.json` | Add `envConfig.*` section |
| 12 | `client/src/i18n/locales/de/system.json` | Add `envConfig.*` section |

---

## Backend Design

### Service: `backend/app/services/env_config.py`

**Variable Registry** - hardcoded list of curated env vars, each with:
```python
@dataclass
class EnvVarDefinition:
    key: str
    category: str        # "application", "security", "database", ...
    input_type: str      # "text" | "number" | "boolean" | "secret"
    default: str | None
    file: str            # "backend" | "client"
```

**Sensitive Detection** - reuse pattern from `admin_db.py`:
```python
SENSITIVE_PATTERN = re.compile(r"password|secret|token|private_key|api_key|encryption_key", re.IGNORECASE)
```

**.env Parser** - line-by-line preserving comments/blanks/order:
- Track each line as comment, blank, or key=value
- On write: update value in-place, preserve structure
- Atomic write via temp file + `os.replace()`

**File Location Logic:**
- Backend: resolve from project root, check `.env` then `.env.production`
- Client: resolve `client/.env`, `client/.env.development`, `client/.env.production`

**Categories for Backend .env:**
- Application & Mode: `NAS_MODE`, `DEBUG`, `VCL_STORAGE_PATH`
- Logging: `LOG_LEVEL`, `LOG_FORMAT`
- Security: `SECRET_KEY`, `TOKEN_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `REGISTRATION_ENABLED`
- Database: `DATABASE_URL`, `DATABASE_TYPE`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- Admin User: `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`
- CORS & Server: `CORS_ORIGINS`, `FRONTEND_PORT`, `ENFORCE_LOCAL_ONLY`, `ALLOW_PUBLIC_PROFILE_LIST`, `PUBLIC_URL`
- Storage & Backup: `NAS_STORAGE_PATH`, `NAS_QUOTA_BYTES`, `NAS_BACKUP_PATH`, `NAS_BACKUP_RETENTION_DAYS`, `NAS_BACKUP_MAX_COUNT`, `BACKUP_AUTO_ENABLED`, `BACKUP_AUTO_INTERVAL_HOURS`, `BACKUP_AUTO_TYPE`
- VPN: `VPN_ENCRYPTION_KEY`, `VPN_LAN_NETWORK`, `VPN_LAN_INTERFACE`, `VPN_INCLUDE_LAN`, `VPN_CONFIG_PATH`
- Monitoring: `MONITORING_SAMPLE_INTERVAL`, `MONITORING_BUFFER_SIZE`, `MONITORING_DB_PERSIST_INTERVAL`, `MONITORING_DEFAULT_RETENTION_HOURS`
- Power: `POWER_MANAGEMENT_ENABLED`, `POWER_DEFAULT_PROFILE`, `POWER_AUTO_SCALING_ENABLED`, CPU thresholds
- Fan: `FAN_CONTROL_ENABLED`, `FAN_MIN_PWM_PERCENT`, `FAN_EMERGENCY_TEMP_CELSIUS`, `FAN_SAMPLE_INTERVAL_SECONDS`
- RAID: `RAID_*`, `SMART_SCAN_*`
- WebDAV: `WEBDAV_ENABLED`, `WEBDAV_PORT`, `WEBDAV_SSL_ENABLED`
- Samba: `SAMBA_SHARES_CONF_PATH`
- Email: `EMAIL_ENABLED`, `SMTP_*`, `EMAIL_FROM_*`
- Mobile: `MOBILE_SERVER_URL`, `MOBILE_PAIRING_ALLOW_LAN`
- Cloud: `CLOUD_IMPORT_ENABLED`, Google/Microsoft OAuth credentials
- Network: `MDNS_HOSTNAME`
- Pi-hole: `PIHOLE_ENABLED`, `PIHOLE_WEB_PORT`
- BaluPi: `BALUPI_ENABLED`, `BALUPI_URL`, `BALUPI_HANDSHAKE_SECRET`
- Notifications: `NOTIFICATION_RETENTION_DAYS`, `WS_HEARTBEAT_INTERVAL`
- Sleep: `SLEEP_MODE_ENABLED`

**Client .env:** `VITE_API_BASE_URL`, `VITE_BUILD_TYPE`

### Schemas: `backend/app/schemas/env_config.py`

```python
class EnvVarResponse(BaseModel):
    key: str
    value: str              # "********" for sensitive
    is_sensitive: bool
    category: str
    description: str        # i18n key, not raw text
    input_type: str         # text | number | boolean | secret
    default: str | None
    file: str               # backend | client

class EnvConfigReadResponse(BaseModel):
    backend: list[EnvVarResponse]
    client: list[EnvVarResponse]
    categories: list[str]

class EnvVarUpdate(BaseModel):
    key: str                # Validated: A-Z0-9_ only
    value: str

class EnvConfigUpdateRequest(BaseModel):
    file: str               # "backend" | "client"
    updates: list[EnvVarUpdate]
```

### Routes: `backend/app/api/routes/env_config.py`

Pattern: follow `rate_limit_config.py` (admin-only, rate-limited, audit-logged).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/env-config` | Read all vars (sensitive redacted) |
| PUT | `/env-config` | Update vars in specified file |
| GET | `/env-config/reveal/{key}` | Reveal single sensitive value |

All endpoints:
- `Depends(get_current_admin)`
- `@user_limiter.limit(get_limit("admin_operations"))`
- Audit logging via `get_audit_logger_db()`

Route registration in `__init__.py`:
```python
api_router.include_router(env_config.router, prefix="/admin", tags=["admin"])
```
-> Final paths: `/api/admin/env-config`, `/api/admin/env-config/reveal/{key}`

### Security

- Admin-only access via dependency injection
- Rate limiting on all endpoints
- Sensitive values redacted in GET, only revealed via explicit `/reveal/{key}` (audit-logged separately)
- Key whitelist: only curated registry keys accepted (no arbitrary .env manipulation)
- Value validation: type-specific (number/boolean/non-empty for required)
- Audit log: `env_config_read`, `env_config_revealed`, `env_config_updated` (with redacted diffs)
- Atomic writes to prevent corruption
- File paths hardcoded (not user-supplied)

---

## Frontend Design

### API Client: `client/src/api/env-config.ts`

Typed functions using `apiClient` from `lib/api.ts`:
- `getEnvConfig()` -> `EnvConfigResponse`
- `updateEnvConfig(request)` -> void
- `revealEnvVar(key)` -> string

### Component: `client/src/components/env-config/SystemVariablesTab.tsx`

**Layout (top to bottom):**

1. **Warning Banner** (always visible, amber/red)
   - `AlertTriangle` icon
   - "Editing these values directly modifies .env config files. Incorrect values may prevent the system from starting."

2. **File Tabs** - Toggle "Backend (.env)" / "Frontend (.env)"

3. **Category Accordions** - grouped cards, collapsible
   - Category header with name + variable count
   - Each variable row:
     - Label (key name)
     - Description text (from i18n)
     - Input based on `input_type`:
       - `text` -> text input
       - `number` -> number input
       - `boolean` -> toggle switch
       - `secret` -> password input with eye icon (calls `/reveal/{key}` on click)
     - Default value hint
     - Modified indicator (dot/badge)

4. **Action Bar** (sticky bottom or top)
   - "Save Changes" button (disabled when no changes)
   - "Discard Changes" button
   - Unsaved changes count

5. **Restart Banner** (shown after save, dismissible, yellow)
   - "Changes saved. A restart may be required for changes to take effect."

**State management:** `useState` for modified values map, loading, reveal states.

### SystemControlPage Integration

In `SystemControlPage.tsx`:
- Add `'envconfig'` to `TabType` union
- Add tab to `system` category: `{ id: 'envconfig', labelKey: 'systemControl.tabs.envConfig', icon: <Variable /> }`
- Add render: `{activeTab === 'envconfig' && <SystemVariablesTab />}`
- Import `Variable` from lucide-react

---

## i18n

### `common.json` (en/de)

```
systemControl.tabs.envConfig = "System Variables" / "Systemvariablen"
```

### `system.json` (en/de) - new `envConfig` section

Keys needed:
- `envConfig.warning.title` / `.message` - danger warning
- `envConfig.warning.restartTitle` / `.restartMessage` - restart notice
- `envConfig.files.backend` / `.client` - file section labels
- `envConfig.categories.*` - all category names (application, security, database, etc.)
- `envConfig.labels.*` - UI labels (currentValue, default, sensitive, modified, reveal, hide)
- `envConfig.actions.*` - save, discard, refresh
- `envConfig.toasts.*` - success/error messages
- `envConfig.descriptions.*` - per-variable descriptions (keyed by env var name)

---

## Implementation Order

1. Backend service (`env_config.py` service) - core logic
2. Backend schemas (`env_config.py` schema)
3. Backend routes + registration
4. Frontend API client
5. i18n translations (en + de, common + system)
6. Frontend component
7. SystemControlPage integration

## Verification

1. Start dev server (`python start_dev.py`)
2. Login as admin, navigate to System Control → System → System Variables
3. Verify all categories and variables load correctly
4. Test reveal toggle on sensitive values
5. Modify a non-sensitive value, save, verify .env file was updated
6. Verify restart warning appears after save
7. Verify audit log entries in Logging page
8. Test with German locale - all strings translated
9. Test error handling: invalid value, network error

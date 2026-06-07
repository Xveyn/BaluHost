# NFS Network Shares — Design

> Status: approved (2026-06-07). Next step: implementation plan via writing-plans.
> Tracks GitHub issue #183 (NFS support incomplete — backend service + UI missing).

## Goal

"Netzlaufwerk-Management" is half-delivered: SMB/CIFS is complete, NFS is entirely
missing (no backend service, routes, or UI). This adds NFS as **admin-defined,
host-based exports**, parallel to the existing Samba feature but with NFS's own
model (NFS has no per-user passwords — it is host/subnet-trust based).

After this work an admin can create/edit/delete NFS exports (a path within the
storage root, the allowed clients, read-only vs read-write, root-squash) from the
System Control page; the server regenerates `/etc/exports.d/baluhost.exports` and
reloads it via `exportfs -ra`. Regular users are unaffected (admin-only feature).

## Why NFS differs from Samba (context)

Samba (`samba_service.py`) is **per-user**: it derives shares from the
`User.smb_enabled` flag and syncs `smbpasswd`. NFS has no per-user password
concept — exports are granted to hosts/subnets. So NFS cannot reuse the user
model; it needs its own persisted export records (a new table + CRUD). Everything
else mirrors Samba: async service with dev-mode no-ops, regenerate-config-from-DB
+ reload, admin-only routes, sudoers-scoped privileged command, a setup script,
and a management card in `SystemControlPage.tsx`.

## Approach

**DB table → regenerate exports file → `exportfs -ra`** (mirrors Samba's
regenerate-from-DB pattern). The `nfs_exports` table is the source of truth; the
service writes `/etc/exports.d/baluhost.exports` atomically and reloads.

Rejected alternatives: parsing/editing `/etc/exports` directly (fragile, no
dev-mode story, weak validation); a JSON state file under storage (inconsistent
with the codebase's DB convention — Samba uses the DB).

## Scope

In scope: admin CRUD of NFS exports; one client spec + one mode (ro/rw) +
root-squash per export; config generation + reload; status; sudoers + setup
script; UI card next to Samba; tests.

Out of scope (YAGNI): multiple host-rules per export, `all_squash`/anon UID/GID
mapping, `sync`/`async` toggle (fixed to `sync`), active client-mount listing
(`showmount -a`), moving Samba to a separate page.

## Design

### 1. Data model + migration

New model `backend/app/models/nfs_export.py` → table `nfs_exports`:

| column | type | notes |
|---|---|---|
| `id` | int PK | also used as the export's `fsid` |
| `path` | str | relative to storage root; `""` = whole root; `UNIQUE` |
| `clients` | str | one spec: IPv4, CIDR, hostname, or `*` |
| `read_only` | bool | default `False` (rw) |
| `root_squash` | bool | default `True` |
| `enabled` | bool | default `True` — only enabled rows are exported |
| `comment` | str opt | free text |
| `created_at` / `updated_at` | datetime(tz) | `server_default=func.now()` |

- Registered in `models/__init__.py` (import + `__all__`).
- Alembic migration created with `alembic revision --autogenerate`, then the
  `down_revision` **manually re-pointed onto the real current `alembic heads`**
  (not the stale dev-DB head) to avoid a multi-head prod-deploy failure.

### 2. Backend service (`backend/app/services/nfs_service.py`)

Async functions; **all system commands are no-ops in dev mode** (return sensible
values), matching `samba_service.py`.

- `_validate_export_path(path) -> str`: reject `..`, normalize via `PurePosixPath`,
  ensure the resolved absolute path stays within `settings.nas_storage_path`;
  return the absolute path. Defense-in-depth (Pydantic also validates).
- `_validate_clients(clients)`: regex allowing IPv4, IPv4/CIDR, DNS hostname, or
  `*`. Raise `ValueError` on anything else.
- `_get_exports_conf_path()`: `getattr(settings, "nfs_exports_conf_path",
  "/etc/exports.d/baluhost.exports")` (mirrors samba's `_get_shares_conf_path`).
- `regenerate_exports_config(db) -> bool`: query `enabled` exports, build one line
  per export, atomic tmp+rename write. Line format:
  `<abs_path> <clients>(<rw|ro>,<root_squash|no_root_squash>,sync,no_subtree_check,fsid=<id>)`.
  The fixed `fsid=<id>` lets both NFSv3 and NFSv4 clients mount without pseudo-root
  setup. Dev mode: log + return `True`.
- `apply_exports() -> bool`: `sudo exportfs -ra` via `asyncio.create_subprocess_exec`
  (no shell). Dev mode: return `True`.
- `get_nfs_status(db) -> dict`: `{is_running, version, exports_count}`. Running via
  `systemctl is-active nfs-server` (fallback `pgrep nfsd`); `exports_count` from DB.
  Dev mode: `{is_running: False, version: "dev-mode", exports_count: <db count>}`.

### 3. Schemas + routes

`backend/app/schemas/nfs.py`:
- `NfsExportResponse` (all columns + computed `mount_target`).
- `NfsExportCreate` / `NfsExportUpdate` (`path`, `clients`, `read_only`,
  `root_squash`, `enabled`, `comment`) with `field_validator`s mirroring the
  service validators (reject traversal / bad client spec).
- `NfsExportsResponse` (`exports: list[...]`).
- `NfsStatusResponse` (`is_running`, `version`, `exports_count`).

`backend/app/api/routes/nfs.py` — `router = APIRouter(prefix="/nfs", tags=["nfs"])`,
every route `Depends(deps.get_current_admin)`, `@user_limiter.limit(get_limit("admin_operations"))`,
Pydantic bodies, registered in `routes/__init__.py`:
- `GET /nfs/status` → `NfsStatusResponse`
- `GET /nfs/exports` → `NfsExportsResponse`
- `POST /nfs/exports` → create → `regenerate_exports_config` → `apply_exports`
- `PUT /nfs/exports/{id}` → update → regenerate → apply
- `DELETE /nfs/exports/{id}` → delete → regenerate → apply

`mount_target` is computed as `<server-ip>:<abs_path>` (server IP via the same
`_get_local_ip()` helper Samba uses) so the UI can render a copy-paste
`sudo mount -t nfs <mount_target> /mnt/baluhost`.

### 4. Security / sudoers / deploy

- Admin-only + rate-limited + Pydantic-validated. Path jail blocks exports outside
  the storage root. UI carries a **LAN-only warning** (NFS has no per-user auth).
- `deploy/nfs/baluhost-nfs-sudoers`:
  `<service_user> ALL=(ALL) NOPASSWD: /usr/sbin/exportfs -ra` and `… exportfs -r`
  (explicit args — tighter than Samba's binary-only entries). The exports file is
  owned by the service user (written without sudo); only the reload needs sudo.
- `deploy/nfs/setup-nfs.sh`: install `nfs-kernel-server`; pre-create
  `/etc/exports.d/baluhost.exports` chowned to the service user (mode 644);
  install sudoers (`visudo -c`); `systemctl enable --now nfs-server`.

### 5. Frontend

- `client/src/api/nfs.ts`: typed interfaces (`NfsExport`, `NfsStatus`,
  `NfsExportCreate`/`Update`) + functions (`getNfsStatus`, `listNfsExports`,
  `createNfsExport`, `updateNfsExport`, `deleteNfsExport`) — follows
  `api/CLAUDE.md` (apiClient, `/api/nfs/...`, return `data`).
- `client/src/components/nfs/NfsManagementCard.tsx`: status header
  (running + export count), export list (path, clients, mode badge, squash,
  enabled), add/edit dialog, delete with confirm, LAN-only warning banner, and a
  copy-paste mount example per export. Mirrors `SambaManagementCard.tsx` structure.
- Rendered next to `SambaManagementCard` in `client/src/pages/SystemControlPage.tsx`.
- i18n keys added under a `nfs` area in the existing locale files (de + en).

### 6. Tests

- `backend/tests/services/test_nfs_service.py`: dev-mode stubs return sensible
  values; non-dev `regenerate_exports_config` writes correct export lines
  (monkeypatched conf path + settings, like `test_samba_service.py`); path
  validator rejects `..`/outside-root; clients validator rejects malformed specs.
- `backend/tests/api/test_nfs_routes.py`: non-admin → 403 on every route; CRUD
  happy path (create → list → update → delete); create with bad path/clients → 422.
- Frontend Vitest: `api/nfs` call shapes + `NfsManagementCard` (renders an export
  list from mocked API; "add export" calls `createNfsExport`).

## Data flow

```
Admin → SystemControlPage → NfsManagementCard
  → api/nfs.createNfsExport(...)
    → POST /api/nfs/exports  (admin-gated, validated)
      → persist NfsExport row
      → regenerate_exports_config(db)  → writes /etc/exports.d/baluhost.exports
      → apply_exports()                → sudo exportfs -ra
    ← NfsExportResponse (incl. mount_target)
  ← list refreshes; card shows mount example
```

## Files touched

New (backend): `models/nfs_export.py`, `schemas/nfs.py`, `services/nfs_service.py`,
`api/routes/nfs.py`, an Alembic migration, `tests/services/test_nfs_service.py`,
`tests/api/test_nfs_routes.py`.
New (deploy): `deploy/nfs/baluhost-nfs-sudoers`, `deploy/nfs/setup-nfs.sh`.
New (frontend): `client/src/api/nfs.ts`, `client/src/components/nfs/NfsManagementCard.tsx`,
plus a Vitest test.
Modified: `models/__init__.py` (register model), `api/routes/__init__.py` (register
router), `client/src/pages/SystemControlPage.tsx` (render card), de/en locale files.
</content>

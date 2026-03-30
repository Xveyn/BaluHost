# Compatibility Layer

Bridges between BaluHost (FastAPI/ASGI) and third-party WSGI libraries. Currently used exclusively for WebDAV integration.

## Files

- `__init__.py` — Python 3.14+ asyncio patches (`apply_asyncio_patches`): fixes `iscoroutinefunction` detection and suppresses deprecation warnings for `get_event_loop_policy`
- `webdav_asgi.py` — Standalone WsgiDAV application with BaluHost auth. Contains `BaluHostDomainController` (authenticates against User table via bcrypt) and `RequestLoggingMiddleware`
- `webdav_provider.py` — Custom WsgiDAV filesystem provider with per-user root isolation. Admin sees full storage, regular users see only their home directory. Reports disk quota from storage root for correct Windows drive capacity display

## Key Patterns

- WebDAV auth is **password-based** (HTTP Basic), not JWT — it queries the `users` table directly
- User isolation in `BaluHostDAVProvider._loc_to_file_path()` uses `baluhost.user_role` from WSGI environ
- Path traversal protection via `os.path.normpath` + prefix check
- Disk quota reported from `_storage_root` (not per-folder), so Windows clients show RAID array capacity
- WebDAV runs as a separate process managed by `webdav_worker`, not inside the FastAPI app

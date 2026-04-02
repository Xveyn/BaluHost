# Schemas

Pydantic v2 models for API request/response validation. One file per feature domain, mirroring the `models/` and `routes/` structure.

## Conventions

- Inherit from `pydantic.BaseModel`
- Use `field_validator` for custom validation (not `validator` — that's Pydantic v1)
- Naming: `*Request` for input, `*Response` for output, `*InDB` for DB representations, `*Public` for safe external exposure
- Separate request and response schemas — never expose internal fields (hashed passwords, encryption keys) in responses
- Shared validators go in `validators.py`

## Key Schemas

**Auth** (`auth.py`): `LoginRequest`, `RegisterRequest` (with password strength validation), `TokenPayload`, `TokenResponse`, `ChangePasswordRequest`, 2FA schemas. Password policy: 8-128 chars, uppercase + lowercase + digit, 11-entry blacklist

**User** (`user.py`): `UserPublic` (safe for API responses — no password hash)

**Files** (`files.py`): `FileItem`, `FileListResponse` — file/folder representations for the file manager

**System** (`system.py`): `SystemInfo` — hardware and OS information

**Monitoring** (`monitoring.py`): CPU, memory, network, disk I/O sample schemas

**Power** (`power.py`): `PowerProfile` enum (IDLE/LOW/MEDIUM/SURGE), `ServicePowerProperty`, profile configs

**Power Permissions** (`power_permissions.py`): `UserPowerPermissionsResponse`, `UserPowerPermissionsUpdate`, `MyPowerPermissionsResponse` — per-user power action delegation

## Adding a Schema

1. Create `schemas/my_feature.py`
2. Define request/response models with type hints and `Field()` descriptions
3. Add validators using `@field_validator` for input validation
4. Import in `__init__.py` if the schema is commonly used across modules
5. Reference in route handlers as type annotations for automatic OpenAPI docs

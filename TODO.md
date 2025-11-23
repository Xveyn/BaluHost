# TODO – User Ownership & Permissions

## Backend
- [x] Extend file persistence (DB or storage metadata) with an `ownerId` field.
- [x] Ensure authentication middleware populates `req.user` / request context with ID and roles.
- [x] Add authorization helpers for ownership and elevated roles (e.g., admin, manager).
- [x] Update upload endpoints to assign the current user as file owner on create.
- [x] Restrict read/update/delete endpoints to owners or privileged roles.
- [x] Add/extend automated tests covering owner access, forbidden access, and admin overrides.
- [ ] Update telemetry/logging to surface unauthorized access attempts.

## Frontend
- [x] Update API client types to include owner metadata in file responses.
- [x] Gate file actions (view/edit/delete) based on ownership/role in UI components (e.g., `FileManager`).
- [x] Surface owner information and meaningful error feedback to the user.
- [ ] Exercise manual test plan in dev mode (owner vs non-owner vs admin).

## Documentation & Ops
- [ ] Document new permission model and API changes in `README.md` / API docs.
- [ ] Communicate migration or seed steps for environments.
- [ ] Capture open questions or follow-ups after implementation.

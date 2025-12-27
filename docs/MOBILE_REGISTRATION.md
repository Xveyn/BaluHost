Mobile Device Registration — QR / Token Flow

Overview

This document describes the secure mobile-device registration flow used by BaluHost.
Registration uses a one-time token (QR-code) generated from the server UI (localhost) and consumed by mobile apps. Tokens are single-use and bound to the generating user.

Flows

1) Generate a registration token (desktop / server UI)
- This endpoint must be called from localhost for security (`/api/mobile/token/generate`). It returns a short-lived token and a QR payload that the mobile app scans.

Example (desktop / server):

```bash
curl -X POST "http://localhost:8000/api/mobile/token/generate?include_vpn=false&device_name=My%20Laptop" \
  -H "Authorization: Bearer <USER_TOKEN>"
```

Response (JSON):
- `token`: registration token (string)
- `server_url`: URL mobile should use (e.g. `http://192.168.1.10:8000`)
- `expires_at`: ISO timestamp
- `qr_code`: base64 PNG image (optional)

The server will often render a QR containing JSON like:

```json
{
  "token": "reg_xxx...",
  "server": "http://192.168.1.10:8000",
  "expires_at": "2025-12-27T12:34:56Z",
  "device_token_validity_days": 90
}
```

2) Mobile app: scan QR and register
- The mobile app extracts `token` and `server` from the QR JSON and calls `POST /api/mobile/register` on the discovered `server`.
- Body JSON example:

```json
{
  "token": "reg_xxx...",
  "device_info": {
    "device_name": "Pixel 6",
    "device_type": "android",
    "device_model": "Pixel 6",
    "os_version": "Android 13",
    "app_version": "1.2.3"
  },
  "token_validity_days": 90,
  "push_token": "<optional-fcm-token>"
}
```

Example curl (mobile / test):

```bash
curl -X POST "http://192.168.1.10:8000/api/mobile/register" \
  -H "Content-Type: application/json" \
  -d '{"token":"reg_xxx","device_info":{"device_name":"Phone","device_type":"android","device_model":"Pixel","os_version":"Android 13","app_version":"1.0"}}'
```

Response: access and refresh tokens, `user` and registered `device` metadata. Save tokens in the app's secure storage.

3) Desktop client (native) registration using the token
- Desktop/other clients that perform `POST /api/sync/register` must also include the registration token and authenticate as the same user who generated the token.
- Two supported ways to provide the token to `/api/sync/register`:
  - Include `registration_token` as a field in the JSON body
  - Or include header `X-Registration-Token: <token>`

Example curl (desktop sync client):

```bash
curl -X POST "http://192.168.1.10:8000/api/sync/register" \
  -H "Authorization: Bearer <USER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"laptop-123","device_name":"Work Laptop","registration_token":"reg_xxx"}'
```

Or with header:

```bash
curl -X POST "http://192.168.1.10:8000/api/sync/register" \
  -H "Authorization: Bearer <USER_TOKEN>" \
  -H "X-Registration-Token: reg_xxx" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"laptop-123","device_name":"Work Laptop"}'
```

Notes and Security

- Tokens are single-use and short-lived. The server will reject reused or expired tokens.
- Tokens are tied to the user that generated them; the authenticated user performing the `/api/sync/register` call must match the token owner.
- `POST /api/mobile/token/generate` is restricted to localhost for security. Use the web UI on the server (or the server's local IP in dev) to create tokens.
- For automation or CI, generate tokens from a trusted environment that can access localhost on the server.

Android Developer Guidance — Quick Snippets

1) Parse QR JSON (Kotlin)

```kotlin
import com.google.gson.Gson

val qrJson = /* scanned QR payload string */
val qr = Gson().fromJson(qrJson, com.baluhost.android.data.remote.dto.RegistrationQrData::class.java)
val token = qr.token
val serverUrl = qr.server
```

2) Use existing `RegisterDeviceUseCase` (project already contains it)
- The app ships `RegisterDeviceUseCase` which performs the dynamic Retrofit call and POST to `/api/mobile/register`.
- Example usage:

```kotlin
val result = registerDeviceUseCase(token = qr.token, serverUrl = qr.server, deviceName = "${Build.MANUFACTURER} ${Build.MODEL}")
if (result is Result.Success) {
  // Save tokens and proceed
}
```

3) If you need to call `/api/sync/register` from native desktop code, include the `registration_token` field in the JSON or `X-Registration-Token` header and authenticate as the token owner.

Testing

- Generate a token with `curl` on the server (localhost), scan QR with mobile, register the device — verify mobile `/api/mobile/devices` shows the new device.
- For desktop registration testing, use the same token to POST to `/api/sync/register` with an Authorization header for the same user.

If you want, I can add an example UI flow in the Android app (scan + auto-register) or add integration tests for token validation on the backend.

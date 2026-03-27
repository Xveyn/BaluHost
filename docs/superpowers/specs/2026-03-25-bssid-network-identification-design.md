# BSSID-based Home Network Identification

**Date:** 2026-03-25
**Status:** Draft
**Scope:** BaluApp (Android/Kotlin) only — no backend changes

## Problem

The BaluApp needs to quickly determine whether the smartphone is on the same local network as the NAS to decide between direct LAN connection and VPN. Currently there is no mechanism for this; the app just uses whichever server URL it has.

## Solution

During QR code pairing (when the user is on their home WiFi), the app captures the current WiFi BSSID (router MAC address) and stores it locally. On subsequent app starts, the app compares the current BSSID against the stored one to instantly determine network location.

## Design

### Flow

1. User scans QR code while on home WiFi
2. App registers with the server (existing flow, unchanged)
3. App reads current BSSID via `ConnectivityManager` (API 31+) or `WifiManager` (legacy)
4. App stores `home_bssid` + `server_url` locally (DataStore)
5. On each app start:
   - Read current BSSID
   - Compare against stored `home_bssid` (uppercase, colon-separated)
   - Match: "Home network" — use direct LAN connection via `server_url`
   - No match: "External" — VPN connection required (app uses LAN IP through VPN tunnel)

### Connection Strategy

The QR code contains a `server` field with the LAN URL (e.g. `http://192.168.1.100:8000`). When VPN is active, the LAN IP is routable through the VPN tunnel (WireGuard `AllowedIPs` includes the LAN subnet). The detection result maps to:

| NetworkLocation | Connection Strategy |
|-----------------|-------------------|
| `HOME` | Direct HTTP to `server_url` (LAN) |
| `EXTERNAL` | Activate VPN, then HTTP to same `server_url` (routed through tunnel) |
| `UNKNOWN` | Reachability probe to decide, then same as HOME or EXTERNAL |

The app always uses the same `server_url` — VPN routing makes it reachable from external networks.

### Permissions

| Android Version | Permission Required | Notes |
|-----------------|-------------------|-------|
| Android 13+ (API 33+) | `NEARBY_WIFI_DEVICES` | Declare with `usesPermissionFlags="neverForLocation"` — no location prompt |
| Android <13 | `ACCESS_FINE_LOCATION` | Required by OS to read BSSID |

### Permission Declaration (AndroidManifest.xml)

```xml
<uses-permission
    android:name="android.permission.NEARBY_WIFI_DEVICES"
    android:usesPermissionFlags="neverForLocation"
    android:minSdkVersion="33" />
<uses-permission
    android:name="android.permission.ACCESS_FINE_LOCATION"
    android:maxSdkVersion="32" />
<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
```

### Local Data Storage

```kotlin
// In DataStore (or SharedPreferences)
home_bssid: String?     // e.g. "AA:BB:CC:DD:EE:FF" (uppercase, colon-separated), null if not captured
home_server_url: String // e.g. "http://192.168.1.100:8000" (from QR code)
```

No database models, migrations, or API changes required.

### BSSID Read Logic (Kotlin)

`WifiManager.connectionInfo` is deprecated since API 31 (Android 12). Use `ConnectivityManager` on modern devices:

```kotlin
fun getCurrentBssid(context: Context): String? {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        // Android 12+ — use ConnectivityManager
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return null
        val caps = cm.getNetworkCapabilities(network) ?: return null
        val wifiInfo = caps.transportInfo as? WifiInfo ?: return null
        val bssid = wifiInfo.bssid
        if (bssid == null || bssid == "02:00:00:00:00:00") return null
        return bssid.uppercase()
    } else {
        // Legacy path (API < 31)
        val wifiManager = context.getSystemService(Context.WIFI_SERVICE) as WifiManager
        @Suppress("DEPRECATION")
        val info = wifiManager.connectionInfo
        val bssid = info.bssid
        if (bssid == null || bssid == "02:00:00:00:00:00") return null
        return bssid.uppercase()
    }
}
```

### Network Detection Logic

```kotlin
enum class NetworkLocation { HOME, EXTERNAL, UNKNOWN }

fun detectNetworkLocation(context: Context, storedBssid: String?): NetworkLocation {
    if (storedBssid == null) return NetworkLocation.UNKNOWN
    val currentBssid = getCurrentBssid(context) ?: return NetworkLocation.UNKNOWN
    return if (currentBssid == storedBssid) NetworkLocation.HOME else NetworkLocation.EXTERNAL
}
```

### Integration Point: After QR Code Registration

In the existing registration success callback:

```kotlin
// After successful registration response
val bssid = getCurrentBssid(context)
if (bssid != null) {
    dataStore.saveHomeBssid(bssid)  // stored uppercase, colon-separated
}
dataStore.saveServerUrl(registrationResponse.serverUrl)
```

### Fallback: Permission Denied or No WiFi

When BSSID is unavailable (permission denied, cellular connection, WiFi disabled, etc.):
- `detectNetworkLocation()` returns `UNKNOWN`
- App falls back to reachability probe: `GET /api/ping` (unauthenticated, ultra-lightweight health endpoint)
  - Response within 500ms: treat as home network (LAN responses are typically <50ms)
  - Timeout/failure: treat as external
  - No retry — single attempt. If NAS is in sleep mode, both LAN and VPN will fail; sleep/WoL handling is a separate concern

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Pairing over cellular (not WiFi) | BSSID = null, not stored. Reachability fallback on all future starts |
| Router replaced (new BSSID) | Mismatch — app reports "External". Fix via re-pairing or "Set Home Network" in settings |
| Mesh network (multiple APs) | Only pairing-time AP's BSSID stored. Other APs trigger reachability fallback (~500ms delay). Multi-BSSID deferred to v2 |
| Permission denied at runtime | Graceful degradation to reachability probe |
| BSSID = "02:00:00:00:00:00" | Android placeholder when permission lacking. Treated as null |
| Existing paired devices (pre-feature) | `home_bssid = null` — always uses reachability fallback until user taps "Set Home Network" in settings or re-pairs |
| WiFi disabled but on LAN (tablet/ethernet) | BSSID = null → reachability fallback |
| NAS in sleep mode | Both LAN and VPN fail — handled by existing WoL flow, not by network detection |

### Optional UX: "Set Home Network" Button

App settings should include a "Set Home Network" button that captures and stores the current BSSID. This allows:
- Existing users to set up network detection without re-pairing
- Users who paired over cellular to configure it later
- Quick fix after router replacement

## What This Does NOT Change

- No backend code changes
- No database schema changes
- No API contract changes
- No new QR code fields
- No server-side BSSID storage

## Future Considerations (Out of Scope)

- **Multi-BSSID / Mesh support**: Store a list of known BSSIDs, learned over time when reachability confirms home while BSSID differs
- **Server-side awareness**: Store BSSID on server for cross-device sharing
- **Subnet fallback**: Add `local_subnet` to QR code as secondary check
- **Automatic VPN toggle**: Auto-connect/disconnect VPN based on network detection

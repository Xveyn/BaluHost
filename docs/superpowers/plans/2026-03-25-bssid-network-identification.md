# BSSID-based Home Network Identification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the BaluApp to instantly detect whether the phone is on the home network (LAN) or external, using the WiFi BSSID captured during QR pairing.

**Architecture:** Pure client-side. The app captures the BSSID during QR registration, stores it in DataStore, and compares on each start. Falls back to a reachability probe (`GET /api/ping`) when BSSID is unavailable. No backend changes.

**Tech Stack:** Kotlin, Android DataStore, ConnectivityManager (API 31+), WifiManager (legacy), OkHttp/Retrofit for reachability probe.

**Spec:** `docs/superpowers/specs/2026-03-25-bssid-network-identification-design.md`

**Note:** This plan targets the BaluApp repo ([Xveyn/BaluApp](https://github.com/Xveyn/BaluApp)). File paths use conventional Android project structure — adjust to actual BaluApp package/directory layout.

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `app/src/main/java/.../network/BssidReader.kt` | Read current BSSID (dual-path: ConnectivityManager API 31+ / WifiManager legacy) |
| Create | `app/src/main/java/.../network/NetworkLocationDetector.kt` | Determine HOME / EXTERNAL / UNKNOWN from BSSID + reachability fallback |
| Create | `app/src/main/java/.../data/NetworkPreferences.kt` | DataStore wrapper for `home_bssid` and `home_server_url` |
| Create | `app/src/test/java/.../network/BssidReaderTest.kt` | Unit tests for BSSID reading and normalization |
| Create | `app/src/test/java/.../network/NetworkLocationDetectorTest.kt` | Unit tests for detection logic |
| Modify | `app/src/main/AndroidManifest.xml` | Add permission declarations |
| Modify | Registration success callback (existing) | Capture + store BSSID after QR pairing |
| Modify | App startup / connection logic (existing) | Call `NetworkLocationDetector` to choose connection strategy |
| Modify | Settings screen (existing) | Add "Set Home Network" button |

---

## Task 1: Add WiFi Permissions to AndroidManifest

**Files:**
- Modify: `app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Add permission declarations**

Add inside `<manifest>`, before `<application>`:

```xml
<!-- BSSID-based home network detection -->
<uses-permission
    android:name="android.permission.NEARBY_WIFI_DEVICES"
    android:usesPermissionFlags="neverForLocation"
    android:minSdkVersion="33" />
<uses-permission
    android:name="android.permission.ACCESS_FINE_LOCATION"
    android:maxSdkVersion="32" />
<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
```

- [ ] **Step 2: Verify the app builds**

Run: `./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Commit**

```bash
git add app/src/main/AndroidManifest.xml
git commit -m "feat(network): add WiFi permissions for BSSID-based network detection"
```

---

## Task 2: Create BssidReader

**Files:**
- Create: `app/src/main/java/.../network/BssidReader.kt`
- Create: `app/src/test/java/.../network/BssidReaderTest.kt`

- [ ] **Step 1: Write the failing tests**

```kotlin
// BssidReaderTest.kt
class BssidReaderTest {

    @Test
    fun `normalizeBssid uppercases and keeps colons`() {
        assertEquals("AA:BB:CC:DD:EE:FF", BssidReader.normalizeBssid("aa:bb:cc:dd:ee:ff"))
    }

    @Test
    fun `normalizeBssid returns null for placeholder`() {
        assertNull(BssidReader.normalizeBssid("02:00:00:00:00:00"))
    }

    @Test
    fun `normalizeBssid returns null for null input`() {
        assertNull(BssidReader.normalizeBssid(null))
    }

    @Test
    fun `normalizeBssid returns null for empty string`() {
        assertNull(BssidReader.normalizeBssid(""))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew testDebugUnitTest --tests "*.BssidReaderTest"`
Expected: FAIL — `BssidReader` not found

- [ ] **Step 3: Implement BssidReader**

```kotlin
// BssidReader.kt
package <app_package>.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.wifi.WifiInfo
import android.net.wifi.WifiManager
import android.os.Build

object BssidReader {

    private const val PLACEHOLDER_BSSID = "02:00:00:00:00:00"

    /**
     * Read the current WiFi BSSID.
     * Uses ConnectivityManager on API 31+, WifiManager on older versions.
     * Returns uppercase colon-separated MAC, or null if unavailable.
     */
    fun getCurrentBssid(context: Context): String? {
        val raw = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            readBssidModern(context)
        } else {
            readBssidLegacy(context)
        }
        return normalizeBssid(raw)
    }

    /** Normalize BSSID to uppercase. Returns null for placeholders/invalid values. */
    fun normalizeBssid(bssid: String?): String? {
        if (bssid.isNullOrBlank() || bssid == PLACEHOLDER_BSSID) return null
        return bssid.uppercase()
    }

    private fun readBssidModern(context: Context): String? {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return null
        val caps = cm.getNetworkCapabilities(network) ?: return null
        val wifiInfo = caps.transportInfo as? WifiInfo ?: return null
        return wifiInfo.bssid
    }

    @Suppress("DEPRECATION")
    private fun readBssidLegacy(context: Context): String? {
        val wifiManager = context.applicationContext
            .getSystemService(Context.WIFI_SERVICE) as WifiManager
        return wifiManager.connectionInfo.bssid
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew testDebugUnitTest --tests "*.BssidReaderTest"`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/src/main/java/.../network/BssidReader.kt
git add app/src/test/java/.../network/BssidReaderTest.kt
git commit -m "feat(network): add BssidReader with dual-path API 31+/legacy support"
```

---

## Task 3: Create NetworkPreferences (DataStore)

**Files:**
- Create: `app/src/main/java/.../data/NetworkPreferences.kt`

- [ ] **Step 1: Implement NetworkPreferences**

```kotlin
// NetworkPreferences.kt
package <app_package>.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.networkDataStore by preferencesDataStore(name = "network_prefs")

class NetworkPreferences(private val context: Context) {

    companion object {
        private val KEY_HOME_BSSID = stringPreferencesKey("home_bssid")
        private val KEY_HOME_SERVER_URL = stringPreferencesKey("home_server_url")
    }

    suspend fun saveHomeBssid(bssid: String) {
        context.networkDataStore.edit { prefs ->
            prefs[KEY_HOME_BSSID] = bssid.uppercase()  // normalize for defense-in-depth
        }
    }

    suspend fun getHomeBssid(): String? {
        return context.networkDataStore.data
            .map { prefs -> prefs[KEY_HOME_BSSID] }
            .first()
    }

    suspend fun saveHomeServerUrl(url: String) {
        context.networkDataStore.edit { prefs ->
            prefs[KEY_HOME_SERVER_URL] = url
        }
    }

    suspend fun getHomeServerUrl(): String? {
        return context.networkDataStore.data
            .map { prefs -> prefs[KEY_HOME_SERVER_URL] }
            .first()
    }

    suspend fun clearHomeBssid() {
        context.networkDataStore.edit { prefs ->
            prefs.remove(KEY_HOME_BSSID)
        }
    }
}
```

- [ ] **Step 2: Write instrumented tests (Robolectric or androidTest)**

```kotlin
// NetworkPreferencesTest.kt
@RunWith(RobolectricTestRunner::class)
class NetworkPreferencesTest {

    private lateinit var prefs: NetworkPreferences

    @Before
    fun setup() {
        prefs = NetworkPreferences(ApplicationProvider.getApplicationContext())
    }

    @Test
    fun `saveHomeBssid then getHomeBssid returns same value uppercase`() = runBlocking {
        prefs.saveHomeBssid("aa:bb:cc:dd:ee:ff")
        assertEquals("AA:BB:CC:DD:EE:FF", prefs.getHomeBssid())
    }

    @Test
    fun `getHomeBssid returns null when not set`() = runBlocking {
        assertNull(prefs.getHomeBssid())
    }

    @Test
    fun `clearHomeBssid removes stored value`() = runBlocking {
        prefs.saveHomeBssid("AA:BB:CC:DD:EE:FF")
        prefs.clearHomeBssid()
        assertNull(prefs.getHomeBssid())
    }

    @Test
    fun `saveHomeServerUrl roundtrip`() = runBlocking {
        prefs.saveHomeServerUrl("http://192.168.1.100:8000")
        assertEquals("http://192.168.1.100:8000", prefs.getHomeServerUrl())
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./gradlew testDebugUnitTest --tests "*.NetworkPreferencesTest"`
Expected: FAIL — `NetworkPreferences` not found

- [ ] **Step 4: Verify tests pass after creating NetworkPreferences**

Run: `./gradlew testDebugUnitTest --tests "*.NetworkPreferencesTest"`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/src/main/java/.../data/NetworkPreferences.kt
git add app/src/test/java/.../data/NetworkPreferencesTest.kt
git commit -m "feat(network): add NetworkPreferences DataStore for home BSSID storage"
```

---

## Task 4: Create NetworkLocationDetector

**Files:**
- Create: `app/src/main/java/.../network/NetworkLocationDetector.kt`
- Create: `app/src/test/java/.../network/NetworkLocationDetectorTest.kt`

- [ ] **Step 1: Write the failing tests**

```kotlin
// NetworkLocationDetectorTest.kt
class NetworkLocationDetectorTest {

    @Test
    fun `returns HOME when current BSSID matches stored`() {
        val result = NetworkLocationDetector.detectFromBssid(
            currentBssid = "AA:BB:CC:DD:EE:FF",
            storedBssid = "AA:BB:CC:DD:EE:FF"
        )
        assertEquals(NetworkLocation.HOME, result)
    }

    @Test
    fun `returns EXTERNAL when BSSIDs differ`() {
        val result = NetworkLocationDetector.detectFromBssid(
            currentBssid = "11:22:33:44:55:66",
            storedBssid = "AA:BB:CC:DD:EE:FF"
        )
        assertEquals(NetworkLocation.EXTERNAL, result)
    }

    @Test
    fun `returns UNKNOWN when stored BSSID is null`() {
        val result = NetworkLocationDetector.detectFromBssid(
            currentBssid = "AA:BB:CC:DD:EE:FF",
            storedBssid = null
        )
        assertEquals(NetworkLocation.UNKNOWN, result)
    }

    @Test
    fun `returns UNKNOWN when current BSSID is null`() {
        val result = NetworkLocationDetector.detectFromBssid(
            currentBssid = null,
            storedBssid = "AA:BB:CC:DD:EE:FF"
        )
        assertEquals(NetworkLocation.UNKNOWN, result)
    }

    @Test
    fun `comparison is case-insensitive via normalization`() {
        val result = NetworkLocationDetector.detectFromBssid(
            currentBssid = "AA:BB:CC:DD:EE:FF",
            storedBssid = "aa:bb:cc:dd:ee:ff"
        )
        assertEquals(NetworkLocation.HOME, result)
    }

    @Test
    fun `returns UNKNOWN when both BSSIDs are null (cellular pairing scenario)`() {
        val result = NetworkLocationDetector.detectFromBssid(
            currentBssid = null,
            storedBssid = null
        )
        assertEquals(NetworkLocation.UNKNOWN, result)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew testDebugUnitTest --tests "*.NetworkLocationDetectorTest"`
Expected: FAIL — class not found

- [ ] **Step 3: Implement NetworkLocationDetector**

```kotlin
// NetworkLocationDetector.kt
package <app_package>.network

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

enum class NetworkLocation { HOME, EXTERNAL, UNKNOWN }

object NetworkLocationDetector {

    private const val REACHABILITY_TIMEOUT_MS = 500

    /** Pure BSSID comparison — no I/O, no context needed. */
    fun detectFromBssid(currentBssid: String?, storedBssid: String?): NetworkLocation {
        if (storedBssid == null || currentBssid == null) return NetworkLocation.UNKNOWN
        val normalizedCurrent = currentBssid.uppercase()
        val normalizedStored = storedBssid.uppercase()
        return if (normalizedCurrent == normalizedStored) NetworkLocation.HOME else NetworkLocation.EXTERNAL
    }

    /**
     * Full detection: BSSID check first, reachability probe as fallback.
     * Call from a coroutine scope — the reachability probe runs on IO dispatcher.
     */
    suspend fun detect(
        context: Context,
        storedBssid: String?,
        serverUrl: String?
    ): NetworkLocation {
        val currentBssid = BssidReader.getCurrentBssid(context)
        val bssidResult = detectFromBssid(currentBssid, storedBssid)

        // If BSSID gave a definitive answer, use it
        if (bssidResult != NetworkLocation.UNKNOWN) return bssidResult

        // Fallback: reachability probe
        if (serverUrl == null) return NetworkLocation.UNKNOWN
        return if (isServerReachable(serverUrl)) NetworkLocation.HOME else NetworkLocation.EXTERNAL
    }

    /** Attempt GET /api/ping with a tight timeout. */
    private suspend fun isServerReachable(serverUrl: String): Boolean =
        withContext(Dispatchers.IO) {
            try {
                val url = URL("${serverUrl.trimEnd('/')}/api/ping")
                val conn = url.openConnection() as HttpURLConnection
                conn.connectTimeout = REACHABILITY_TIMEOUT_MS
                conn.readTimeout = REACHABILITY_TIMEOUT_MS
                conn.requestMethod = "GET"
                val code = conn.responseCode
                conn.disconnect()
                code in 200..299
            } catch (_: Exception) {
                false
            }
        }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew testDebugUnitTest --tests "*.NetworkLocationDetectorTest"`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/src/main/java/.../network/NetworkLocationDetector.kt
git add app/src/test/java/.../network/NetworkLocationDetectorTest.kt
git commit -m "feat(network): add NetworkLocationDetector with BSSID match and reachability fallback"
```

---

## Task 5: Integrate BSSID Capture Into QR Registration Flow

**Files:**
- Modify: Registration success callback (find existing file handling QR scan result / registration response)

- [ ] **Step 1: Locate the registration success handler**

Search the codebase for where the QR registration response is handled — look for code that processes the `MobileRegistrationResponse` (access_token, refresh_token, user, device).

- [ ] **Step 2: Add BSSID capture after successful registration**

In the registration success callback, add:

```kotlin
// After successful registration — capture home network BSSID
val networkPrefs = NetworkPreferences(context)
val bssid = BssidReader.getCurrentBssid(context)
if (bssid != null) {
    networkPrefs.saveHomeBssid(bssid)
}
// server_url is already available from the QR code data
networkPrefs.saveHomeServerUrl(qrData.server)
```

This requires the WiFi permission to be granted. Register the permission launcher in `onCreate()` of the Activity/Fragment that handles registration:

```kotlin
// In onCreate() — MUST be registered here, not on-demand
private val bssidPermissionLauncher = registerForActivityResult(
    ActivityResultContracts.RequestPermission()
) { granted ->
    if (granted) {
        // Permission granted — now capture BSSID
        lifecycleScope.launch {
            val bssid = BssidReader.getCurrentBssid(applicationContext)
            if (bssid != null) {
                NetworkPreferences(applicationContext).saveHomeBssid(bssid)
            }
        }
    }
    // If denied: no BSSID stored — app will use reachability fallback.
    // Do NOT re-prompt. User can configure later via Settings > "Set Home Network".
}
```

Then after successful registration, request the permission:

```kotlin
// After registration success — request permission to capture BSSID
val permission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
    Manifest.permission.NEARBY_WIFI_DEVICES
} else {
    Manifest.permission.ACCESS_FINE_LOCATION
}

if (ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED) {
    // Already granted — capture immediately
    lifecycleScope.launch {
        val bssid = BssidReader.getCurrentBssid(applicationContext)
        if (bssid != null) {
            NetworkPreferences(applicationContext).saveHomeBssid(bssid)
        }
    }
} else {
    bssidPermissionLauncher.launch(permission)
}
```

- [ ] **Step 3: Verify on device/emulator**

1. Generate a QR token in the web UI (Mobile Devices page)
2. Scan with BaluApp while on WiFi
3. After registration success, verify via Android Studio debugger or Logcat that `home_bssid` is stored

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(network): capture and store BSSID during QR code registration"
```

---

## Task 6: Integrate Network Detection at App Startup

**Files:**
- Modify: App startup / main activity / connection initialization (find existing file that establishes the server connection)

- [ ] **Step 1: Locate the app startup connection logic**

Search for where the app initializes its API client or decides which server URL to use on launch.

- [ ] **Step 2: Add network detection before connection**

```kotlin
// At app startup, before establishing connection
lifecycleScope.launch {
    val networkPrefs = NetworkPreferences(applicationContext)
    val storedBssid = networkPrefs.getHomeBssid()
    val serverUrl = networkPrefs.getHomeServerUrl()

    val location = NetworkLocationDetector.detect(
        context = applicationContext,
        storedBssid = storedBssid,
        serverUrl = serverUrl
    )

    when (location) {
        NetworkLocation.HOME -> {
            // Direct LAN connection — use server_url as-is
            Log.d("Network", "Home network detected — using direct LAN connection")
        }
        NetworkLocation.EXTERNAL -> {
            // External network — prompt VPN or auto-connect if configured
            Log.d("Network", "External network — VPN required")
        }
        NetworkLocation.UNKNOWN -> {
            // Cannot determine — try direct, fall back to VPN
            Log.d("Network", "Network location unknown — trying direct connection")
        }
    }
}
```

- [ ] **Step 3: Test on device**

1. With WiFi on home network: app should detect HOME
2. With WiFi on different network (e.g. hotspot): app should detect EXTERNAL
3. With WiFi off: app should detect UNKNOWN, then try reachability probe

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(network): detect network location on app startup using BSSID"
```

---

## Task 7: Add "Set Home Network" Button in Settings

**Files:**
- Modify: Settings screen / fragment (find existing settings UI)

- [ ] **Step 1: Add UI element to settings**

Add a "Set Home Network" button (or preference item) to the existing settings screen:

```kotlin
// In settings composable or XML layout
Button(
    onClick = { setHomeNetworkBssid() },
    enabled = isOnWifi
) {
    Text("Set Home Network")
}

// Below: show current status
Text(
    text = if (homeBssid != null) "Home network configured" else "Not configured",
    style = MaterialTheme.typography.bodySmall
)
```

- [ ] **Step 2: Implement the action**

```kotlin
private fun setHomeNetworkBssid() {
    lifecycleScope.launch {
        val bssid = BssidReader.getCurrentBssid(applicationContext)
        if (bssid != null) {
            NetworkPreferences(applicationContext).saveHomeBssid(bssid)
            // Show success toast/snackbar
            showMessage("Home network saved")
        } else {
            // Not on WiFi or permission denied
            showMessage("Connect to your home WiFi first")
        }
    }
}
```

- [ ] **Step 3: Handle permission request if needed**

If WiFi permission hasn't been granted yet, request it when the button is tapped (same permission flow as Task 5).

- [ ] **Step 4: Test on device**

1. Open Settings → tap "Set Home Network" while on WiFi → should succeed
2. Turn off WiFi → tap button → should show "Connect to your home WiFi first"
3. After setting, restart app → should detect HOME

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(network): add 'Set Home Network' button in app settings"
```

---

## Task 8: Final Integration Test

- [ ] **Step 1: Full flow test**

On a real device:
1. Fresh install → pair via QR code on home WiFi → verify BSSID stored
2. Restart app on home WiFi → verify HOME detected
3. Switch to mobile hotspot → restart → verify EXTERNAL detected
4. Turn off WiFi entirely → restart → verify UNKNOWN → reachability fallback
5. Go to Settings → "Set Home Network" → verify updates stored BSSID
6. Deny WiFi permission → restart → verify graceful fallback to UNKNOWN

- [ ] **Step 2: Commit final state**

```bash
git add -A
git commit -m "test(network): verify BSSID-based network detection end-to-end"
```

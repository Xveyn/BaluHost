# Sleep-Aware Sync — Client Integration Guide

After the backend update, both **BaluDesk** (C++/Electron) and **BaluApp** (Kotlin/Android) need changes so automatic syncs respect the admin's sleep schedule.

---

## BaluDesk (Desktop Sync Client)

### 1. `X-Sync-Trigger` Header auf alle Sync-Requests

Jeder HTTP-Request an `/api/sync/*` Endpoints braucht den Header `X-Sync-Trigger`:

| Situation | Header-Wert |
|---|---|
| Geplanter/periodischer Sync (Timer, Schedule) | `auto` |
| User klickt "Jetzt synchronisieren" | `manual` |

**Wo:** Im HTTP-Client (vermutlich `SyncHttpClient` o.ae.) als Default-Header setzen, je nach Ausloeser.

**Ohne diesen Header** behandelt der Server den Request als `manual` (Rueckwaertskompatibilitaet), aber das NAS wird dann bei jedem Sync aus dem Sleep geweckt.

### 2. Preflight-Check vor automatischen Syncs

Vor jedem automatischen Sync-Zyklus `GET /api/sync/preflight` aufrufen:

```json
// Response:
{
    "sync_allowed": false,
    "current_sleep_state": "soft_sleep",
    "sleep_schedule": {
        "enabled": true,
        "sleep_time": "23:00",
        "wake_time": "06:00",
        "mode": "suspend"
    },
    "next_sleep_at": "2026-04-02T23:00:00",
    "next_wake_at": "2026-04-03T06:00:00",
    "block_reason": "sleep_active"
}
```

**Logik:**
- `sync_allowed == true` -> Sync starten
- `sync_allowed == false` -> Sync ueberspringen, `next_wake_at` als naechsten Retry-Zeitpunkt nehmen

**Empfohlen:** Preflight-Response lokal cachen (z.B. 5 Minuten TTL). Bei Connection-Timeout den Cache nutzen.

### 3. 503-Responses behandeln

Falls der Preflight-Check uebersprungen wurde oder veraltet ist, antwortet der Server mit `503`:

```json
{
    "detail": {
        "message": "Sync blocked: NAS is in sleep mode",
        "sleep_state": "soft_sleep",
        "next_wake_at": "2026-04-03T06:00:00",
        "retry_after_seconds": 25200
    }
}
```

Plus HTTP-Header: `Retry-After: 25200`

**Aktion:** Sync pausieren, nach `retry_after_seconds` erneut versuchen. Optional Tray-Notification: "NAS schlaeft, Sync pausiert bis 06:00".

### 4. Offline-Schedule-Awareness

Wenn das NAS gar nicht erreichbar ist (Connection Timeout/Refused):
- Gecachten `sleep_schedule` pruefen
- Aktuelle Uhrzeit im Sleep-Fenster `[sleep_time, wake_time)` -> **nicht aggressiv retrien**, naechsten Retry auf `wake_time` setzen
- Ausserhalb des Sleep-Fensters -> normales Error-Handling (Netzwerkproblem)

**Overlap-Check** (gleiche Logik wie Backend):
```cpp
bool isInSleepWindow(int syncMinutes, int sleepMinutes, int wakeMinutes) {
    if (sleepMinutes == wakeMinutes) return false;
    if (sleepMinutes < wakeMinutes)
        return syncMinutes >= sleepMinutes && syncMinutes < wakeMinutes;
    return syncMinutes >= sleepMinutes || syncMinutes < wakeMinutes;
}
```

---

## BaluApp (Android)

### 1. `X-Sync-Trigger` Header

Im `ApiClient` / Retrofit-Interceptor den Header setzen:

```kotlin
// Bei automatischem Sync (WorkManager, Scheduler):
request.addHeader("X-Sync-Trigger", "auto")

// Bei manuellem Sync (User tippt "Sync"):
request.addHeader("X-Sync-Trigger", "manual")
```

### 2. Preflight-Check

Neuer API-Call im `SyncRepository`:

```kotlin
@GET("api/sync/preflight")
suspend fun getSyncPreflight(): SyncPreflightResponse

data class SyncPreflightResponse(
    val sync_allowed: Boolean,
    val current_sleep_state: String,
    val sleep_schedule: SleepScheduleInfo?,
    val next_wake_at: String?,
    val block_reason: String?
)

data class SleepScheduleInfo(
    val enabled: Boolean,
    val sleep_time: String,
    val wake_time: String,
    val mode: String
)
```

**Im WorkManager Sync-Worker:**
```kotlin
// Vor dem eigentlichen Sync:
val preflight = api.getSyncPreflight()
if (!preflight.sync_allowed) {
    // Naechsten Retry auf next_wake_at setzen
    val delay = calculateDelay(preflight.next_wake_at)
    return Result.retry() // mit backoff bis wake_time
}
// Sonst: normaler Sync
```

### 3. 503-Response-Handling

Im Retrofit Error-Handler:
```kotlin
if (response.code() == 503) {
    val body = response.errorBody()?.parseAs<SyncBlockedResponse>()
    val retryAfter = body?.detail?.retry_after_seconds ?: 3600
    // WorkManager: exponential backoff oder festen Delay setzen
    // UI: Snackbar "NAS schlaeft, Sync pausiert"
}
```

### 4. Offline-Awareness

`sleep_schedule` in SharedPreferences cachen. Wenn NAS nicht erreichbar:
```kotlin
fun isNasProbablySleeping(): Boolean {
    val schedule = cachedSleepSchedule ?: return false
    if (!schedule.enabled) return false
    val now = LocalTime.now()
    val sleep = LocalTime.parse(schedule.sleep_time)
    val wake = LocalTime.parse(schedule.wake_time)
    return if (sleep < wake) now in sleep..wake
           else now >= sleep || now < wake
}
```

Wenn `isNasProbablySleeping() == true` -> kein aggressives Retry, Sync auf `wake_time` verschieben.

---

## Betroffene Endpoints

Diese Endpoints senden 503 bei `X-Sync-Trigger: auto/scheduled` waehrend Sleep:

| Endpoint | Zweck |
|---|---|
| `POST /api/sync/changes` | Delta-Sync |
| `GET /api/sync/state` | File-State |
| `POST /api/sync/upload/start` | Chunked Upload starten |
| `POST /api/sync/upload/{id}/chunk/{n}` | Chunk hochladen |
| `POST /api/sync/upload/{id}/resume` | Upload fortsetzen |
| `POST /api/sync/report-folders` | Folder-Report |

**Nicht betroffen** (funktionieren immer):
- `GET /api/sync/preflight`
- `GET /api/sync/status/{device_id}`
- `/api/sync/schedule/*` (CRUD)
- `/api/sync/selective/*`
- `/api/sync/bandwidth/*`

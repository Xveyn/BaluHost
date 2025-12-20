# Offline Queue System - BaluHost Android App

## Übersicht

Das Offline-Queue-System ermöglicht es der App, Dateioperationen (Upload, Delete, etc.) persistent zu speichern und automatisch zu wiederholen, wenn die Netzwerkverbindung wiederhergestellt wurde.

## Architektur

```
┌────────────────────────────────────────────────────────────┐
│                     FilesViewModel                          │
│  - Erkennt Offline-Status                                   │
│  - Queued Operationen bei Netzwerkfehler                   │
│  - Zeigt Pending Count Badge                                │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────┐
│                 OfflineQueueManager                         │
│  - Singleton Service                                        │
│  - Observiert NetworkMonitor                                │
│  - Auto-Retry bei Reconnect                                 │
│  - Exponential Backoff                                      │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────┐
│            OfflineQueueRepository (Room DB)                 │
│  - Persistente Operation Queue                              │
│  - CRUD Operations                                          │
│  - Flow-based Status Updates                                │
└────────────────────────────────────────────────────────────┘
```

## Features

### ✅ Vollständig Implementiert

1. **Persistent Operation Queue**
   - Room Database Entity: `PendingOperationEntity`
   - Speichert: Operation Type, File Path, Local File Path, Status, Retry Count
   - Überlebt App-Restart und Device-Reboot

2. **Automatic Retry**
   - NetworkMonitor beobachtet Connectivity
   - Auto-Retry bei Reconnect via OfflineQueueManager
   - WorkManager Background-Retry alle 15 Minuten
   - Max 3 Retry-Versuche pro Operation

3. **UI Components**
   - **PendingOperationsScreen**: Vollständige Liste aller Queue-Items
   - **Pending Count Badge**: Live-Update in FilesScreen TopAppBar
   - **Manual Retry/Cancel**: Buttons für jede Operation
   - **Status Badges**: PENDING, RETRYING, FAILED, COMPLETED
   - **Error Messages**: Detaillierte Fehleranzeige

4. **Background Workers**
   - **OfflineQueueRetryWorker**: Periodisches Retry alle 15 Min
   - **OfflineQueueCleanupWorker**: Tägliches Cleanup alter Operations
   - WorkManager mit Hilt-Integration
   - Network-Constraints für Retry-Worker

5. **Operation Types**
   - `UPLOAD`: File-Upload mit lokalem File Path
   - `DELETE`: File-Löschung mit Optimistic UI
   - `RENAME`: Datei umbenennen (vorbereitet)
   - `CREATE_FOLDER`: Ordner erstellen (vorbereitet)
   - `MOVE`: Datei verschieben (vorbereitet)
   - `DELETE`: File-Löschung
   - `RENAME`: Datei umbenennen (TODO)
   - `CREATE_FOLDER`: Ordner erstellen (TODO)
   - `MOVE`: Datei verschieben (TODO)

4. **Status Tracking**
   - `PENDING`: Warten auf Retry
   - `RETRYING`: Gerade in Bearbeitung
   - `COMPLETED`: Erfolgreich abgeschlossen
   - `FAILED`: Max Retries überschritten

5. **UI Integration**
   - Pending Operations Count Badge
   - Automatische Queue bei Offline-Erkennung
   - Optimistic UI Updates bei Delete

## Datenbank Schema

### PendingOperationEntity

```kotlin
@Entity(tableName = "pending_operations")
data class PendingOperationEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    
    val operationType: String,      // UPLOAD, DELETE, RENAME, etc.
    val filePath: String,            // Ziel-Pfad auf Server
    val localFilePath: String? = null,  // Lokale Datei (für Upload)
    val destinationPath: String? = null, // Neuer Name/Pfad (für Rename/Move)
    val operationData: String? = null,   // JSON für zusätzliche Daten
    
    val status: String = "PENDING",  // PENDING, RETRYING, FAILED, COMPLETED
    val retryCount: Int = 0,
    val maxRetries: Int = 3,
    val errorMessage: String? = null,
    
    val createdAt: Instant = Instant.now(),
    val lastRetryAt: Instant? = null,
    val completedAt: Instant? = null
)
```

## Nutzung

### FilesViewModel - Upload mit Auto-Queue

```kotlin
fun uploadFile(file: File, destinationPath: String? = null) {
    viewModelScope.launch {
        val uploadPath = destinationPath ?: _uiState.value.currentPath
        
        // Check network connectivity
        if (!networkMonitor.isCurrentlyOnline()) {
            // Queue für später
            when (val result = offlineQueueManager.queueUpload(file, uploadPath)) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        error = "Keine Verbindung. Upload wird automatisch wiederholt."
                    )
                }
                is Result.Error -> { /* Error handling */ }
            }
            return@launch
        }
        
        // Normaler Upload-Versuch
        val result = uploadFileUseCase(file, uploadPath)
        when (result) {
            is Result.Success -> { /* Success */ }
            is Result.Error -> {
                // Fehlgeschlagen → Queue für Retry
                offlineQueueManager.queueUpload(file, uploadPath)
                _uiState.value = _uiState.value.copy(
                    error = "Upload fehlgeschlagen. Wird automatisch wiederholt."
                )
            }
        }
    }
}
```

### FilesViewModel - Delete mit Optimistic UI

```kotlin
fun deleteFile(filePath: String) {
    viewModelScope.launch {
        if (!networkMonitor.isCurrentlyOnline()) {
            // Queue delete
            when (val result = offlineQueueManager.queueDelete(filePath)) {
                is Result.Success -> {
                    // Optimistically remove from UI
                    val updatedFiles = _uiState.value.files.filter { it.path != filePath }
                    _uiState.value = _uiState.value.copy(files = updatedFiles)
                }
                is Result.Error -> { /* Error */ }
            }
            return@launch
        }
        
        // Online delete attempt
        val result = deleteFileUseCase(filePath)
        when (result) {
            is Result.Success -> { loadFiles(_uiState.value.currentPath) }
            is Result.Error -> {
                // Queue for retry
                offlineQueueManager.queueDelete(filePath)
            }
        }
    }
}
```

### OfflineQueueManager - Automatischer Retry

```kotlin
@Singleton
class OfflineQueueManager @Inject constructor(
    private val offlineQueueRepository: OfflineQueueRepository,
    private val uploadFileUseCase: UploadFileUseCase,
    private val deleteFileUseCase: DeleteFileUseCase,
    private val networkMonitor: NetworkMonitor
) {
    private val scope = CoroutineScope(SupervisorJob())
    
    init {
        // Auto-Retry bei Reconnect
        scope.launch {
            networkMonitor.isOnline.collect { isOnline ->
                if (isOnline) {
                    retryPendingOperations()
                }
            }
        }
    }
    
    suspend fun retryPendingOperations() {
        val pendingOperations = offlineQueueRepository.getPendingOperations().first()
        
        pendingOperations.forEach { operation ->
            if (!operation.hasExceededMaxRetries) {
                retryOperation(operation)
            }
        }
    }
}
```

## UI Components

### Pending Operations Badge

```kotlin
// In TopAppBar
if (uiState.pendingOperationsCount > 0) {
    Badge(
        content = { Text("${uiState.pendingOperationsCount}") }
    ) {
        Icon(Icons.Default.Sync, "Pending sync operations")
    }
}
```

### Snackbar Notifications

```kotlin
LaunchedEffect(uiState.error) {
    uiState.error?.let { error ->
        snackbarHostState.showSnackbar(
            message = error,
            duration = SnackbarDuration.Long
        )
    }
}
```

## Datenfluss

### Upload-Operation (Offline)

```
1. User wählt Datei
   ↓
2. FilesViewModel erkennt Offline-Status
   ↓
3. OfflineQueueManager.queueUpload()
   ↓
4. PendingOperationEntity → Room DB
   ↓
5. Pending Count Flow Update → UI Badge
   ↓
6. Snackbar: "Wird automatisch wiederholt"
```

### Auto-Retry (Reconnect)

```
1. NetworkMonitor detektiert Reconnect
   ↓
2. OfflineQueueManager.retryPendingOperations()
   ↓
3. Für jede PENDING Operation:
   - Status → RETRYING
   - Retry Upload/Delete
   ↓
4. Bei Erfolg:
   - Status → COMPLETED
   - completedAt = now()
   ↓
5. Bei Fehler:
   - retryCount++
   - Status → FAILED (wenn maxRetries erreicht)
   - lastRetryAt = now()
```

## Best Practices

### 1. Lokale Datei-Speicherung

```kotlin
// Upload: Kopiere File in App-Cache für Queue
val cacheFile = File(context.cacheDir, "pending_uploads/${file.name}")
file.copyTo(cacheFile, overwrite = true)

offlineQueueManager.queueUpload(cacheFile, destinationPath)
```

### 2. Cleanup

```kotlin
// Alte Completed Operations löschen (täglich via WorkManager)
class CleanupWorker : Worker() {
    override fun doWork(): Result {
        offlineQueueManager.cleanupOldOperations(daysOld = 7)
        return Result.success()
    }
}
```

### 3. User Notification

```kotlin
// Zeige Notification bei Max Retries
if (operation.hasExceededMaxRetries) {
    showNotification(
        title = "Operation fehlgeschlagen",
        message = "${operation.operationType} für ${operation.filePath} konnte nicht durchgeführt werden."
    )
}
```

## Testing

### Unit Tests

```kotlin
@Test
fun `queueUpload should persist operation in DB`() = runTest {
    val file = File("test.txt")
    val path = "/uploads/test.txt"
    
    offlineQueueManager.queueUpload(file, path)
    
    val pending = pendingOperationDao.getPendingOperationsList()
    assertThat(pending).hasSize(1)
    assertThat(pending[0].operationType).isEqualTo("UPLOAD")
}

@Test
fun `retryOperation should mark as COMPLETED on success`() = runTest {
    val operation = PendingOperation(
        id = 1,
        operationType = OperationType.UPLOAD,
        filePath = "/test.txt",
        status = OperationStatus.PENDING
    )
    
    // Mock success
    `when`(uploadFileUseCase(any(), any())).thenReturn(Result.Success(Unit))
    
    offlineQueueManager.retryOperation(operation)
    
    val updated = pendingOperationDao.getOperationById(1)
    assertThat(updated?.status).isEqualTo("COMPLETED")
}
```

### Integration Tests

```kotlin
@Test
fun `offline upload should auto-retry on reconnect`() = runTest {
    // Simulate offline
    networkMonitor.setOffline()
    
    // Upload file
    viewModel.uploadFile(testFile, "/test.txt")
    
    // Verify queued
    assertThat(offlineQueueRepository.getPendingCount().first()).isEqualTo(1)
    
    // Simulate reconnect
    networkMonitor.setOnline()
    
    // Wait for auto-retry
    advanceTimeBy(1000)
    
    // Verify completed
    assertThat(offlineQueueRepository.getPendingCount().first()).isEqualTo(0)
}
```

## Performance

- **Database**: Room mit Indexes auf `status` und `created_at`
- **Flow Updates**: Nur bei Status-Änderung (distinctUntilChanged)
- **Background Work**: WorkManager mit Constraints (Network, Battery)
- **Periodic Retry**: Alle 15 Minuten bei aktiver Netzwerkverbindung

## Sicherheit

- **File Access**: Lokale Files in App-Cache (geschützt)
- **Token Refresh**: Auto-Retry nur mit gültigem Token
- **Encryption**: Sensitive operationData verschlüsselt (TODO)

## Implementierte Features (COMPLETE)

✅ **UI: Pending Operations Screen** - Vollständige Liste mit Status-Anzeige  
✅ **Manual Retry Button** - In PendingOperationsScreen  
✅ **Manual Cancel Button** - In PendingOperationsScreen  
✅ **WorkManager Integration** - Background-Retry + Cleanup  
✅ **Pending Count Badge** - Live-Update in TopAppBar  
✅ **Status Tracking** - PENDING, RETRYING, FAILED, COMPLETED  
✅ **Error Display** - Detaillierte Fehlermeldungen  

## Optionale Erweiterungen

- [ ] Notification bei Max Retries
- [ ] Batch Operations Support (Multi-Select Upload/Delete)
- [ ] Conflict Resolution (Server-File geändert während Offline)
- [ ] Upload Progress Tracking in Queue
- [ ] Exponential Backoff Strategy (aktuell: Linear)
- [ ] WorkManager Integration für Background-Retry
- [ ] Exponential Backoff Strategy
- [ ] Notification bei Max Retries
- [ ] Batch Operations Support
- [ ] Conflict Resolution (Server-File geändert während Offline)

## Zusammenfassung

Das Offline-Queue-System bietet eine robuste, persistente Lösung für Netzwerkfehler und ermöglicht:

✅ **Automatische Wiederholung** bei Reconnect  
✅ **Persistenz** über App-Restart hinaus  
✅ **Transparenz** durch UI-Badges und Notifications  
✅ **Fehlertoleranz** mit Max-Retry-Limits  
✅ **Optimistic UI** für bessere UX  

Dies verbessert die User Experience erheblich, besonders bei instabilen Netzwerkverbindungen oder Mobile-Data-Wechsel.

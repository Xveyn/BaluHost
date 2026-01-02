# Sync Backend Specification

Version: 0.1
Date: 2025-12-28

Zweck
-----
Dieses Dokument beschreibt die Backend-/Repository-Schnittstellen, Datenmodelle, Fehlercodes und Performance-Anforderungen für die erweiterte Sync- und Migrationsfunktion in der BaluHost Android-App.

Ziele
------
- Erlauben, lokale/externe/cloud-Ordner zu wählen und zu synchronisieren.
- Metriken bereitstellen: Ordnergröße, verfügbarer Speicher, Kopier-/Löschdauer-Histogramme.
- Resumable, verifizierbare Migrationen mit Checkpoints.
- Erweiterbare Cloud-Adapter-Architektur (WebDAV/SMB/Drive).
- Produktionsreife: DI (Hilt), Tests, sichere Speicherung von Credentials.

High-level Architektur
----------------------
- `SyncRepository` (Domain): bietet koroutinische APIs (suspend / Flow) für Folder-Operationen, Metriken, Migration, Queue- und Job-Steuerung.
- `SyncRepositoryImpl` (Data): implementiert die Domain-Schnittstelle und orchestriert LocalHelpers, CloudAdapters, MigrationManager und WorkManager-Worker.
- `CloudAdapter` (Data): Adapter-Interface für entfernte Speicher (list/stat/stream upload/download/delete/space).
- `SyncMigrationManager`: Orchestriert Migrationen mit Checkpoints, Checksums und Wiederaufnahme.
- `SyncMetricsWorker`: periodischer Worker (WorkManager) zur Erhebung von Metriken.

Dateipfade (Ziel)
------------------
- `app/src/main/java/com/baluhost/android/domain/repository/SyncRepository.kt` (Interface Erweiterung)
- `app/src/main/java/com/baluhost/android/data/repository/SyncRepositoryImpl.kt`
- `app/src/main/java/com/baluhost/android/data/cloud/CloudAdapter.kt`
- `app/src/main/java/com/baluhost/android/migration/SyncMigrationManager.kt`
- `app/src/main/java/com/baluhost/android/workers/SyncMetricsWorker.kt`
- `app/src/main/java/com/baluhost/android/data/storage/ExternalStorageHelper.kt`

API / Interface Spezifikationen
-------------------------------
Hinweis: Alle Methoden geben `Result<T>` zurück oder Flows, die `Result`-Wrapper verwenden, um Fehlercodes klar zu übermitteln.

SyncRepository (Erweiterte Methoden)
```kotlin
interface SyncRepository {
    suspend fun validateFolderUri(uri: String): Result<FolderStat>
    suspend fun listFiles(uri: String, recursive: Boolean = false): Result<List<FileEntry>>
    fun observeFolderSize(uri: String): Flow<Result<FolderSize>>
    suspend fun getAvailableCapacity(uri: String): Result<Long>

    // Timed operations return duration + result
    suspend fun copyWithTiming(srcUri: String, dstUri: String): Result<OperationResult>
    suspend fun deleteWithTiming(targetUri: String): Result<OperationResult>

    // Migration orchestration helpers
    suspend fun startMigration(migrationId: String, plan: MigrationPlan): Result<MigrationHandle>
    fun observeMigrationProgress(migrationId: String): Flow<Result<MigrationProgress>>
    suspend fun cancelMigration(migrationId: String): Result<Unit>

    // Metrics
    fun observeMetrics(uri: String): Flow<Result<SyncMetrics>>
}
```

Wichtige Datamodelle
--------------------
- `FolderStat`:
  - `uri: String`
  - `totalSize: Long` (bytes)
  - `itemCount: Int`
  - `lastScanTimestamp: Long`
- `FileEntry`:
  - `uri: String`, `name: String`, `size: Long`, `modifiedAt: Long`, `isDirectory: Boolean`
- `OperationResult`:
  - `success: Boolean`, `durationMs: Long`, `bytesTransferred: Long`, `error: String?`
- `MigrationPlan`:
  - `id: String`, `sourceUri: String`, `targetUri: String`, `strategy: MigrationStrategy`, `options: Map<String,String>`
- `MigrationHandle`:
  - `migrationId: String`, `startTime: Long`, `checkpoint: MigrationCheckpoint?`
- `MigrationProgress`:
  - `migrationId`, `status`, `percent`, `transferredBytes`, `estimatedRemainingMs`, `currentItem`
- `SyncMetrics`:
  - `folderSize: Long`, `freeSpace: Long`, `copyDurations: List<Long>` (recent), `deleteDurations: List<Long>` (recent)

CloudAdapter Interface
----------------------
```kotlin
interface CloudAdapter {
    suspend fun stat(path: String): Result<RemoteStat>
    suspend fun list(path: String): Result<List<RemoteEntry>>
    suspend fun download(remotePath: String, localUri: String): Result<OperationResult>
    suspend fun upload(localUri: String, remotePath: String): Result<OperationResult>
    suspend fun delete(path: String): Result<OperationResult>
    suspend fun getAvailableSpace(): Result<Long>
}
```

Migration Contract & Checkpoints
--------------------------------
- Migration must be resumable. Checkpoints persisted in `PreferencesManager` keyed by `migration_{id}`.
- Checkpoint fields: lastProcessedUri, completedCount, transferredBytes, checksumsVerified boolean.
- Migration must write atomically: upload to temp name -> verify checksum -> rename to final name.
- On cancellation: leave checkpoint so resume restarts from lastProcessedUri.

Metrics Schema
--------------
- Metrics are stored as time-series snapshots limited to last N entries (e.g. 100). Persisted as JSON via `PreferencesManager` keys `sync_metrics_{uri}`.
- Fields: timestamp, folderSize, freeSpace, avgCopyMs, p50CopyMs, p95CopyMs, avgDeleteMs

Error Codes & Retries
---------------------
- Use a small error code enum (TRANSPORT_ERROR, AUTH_ERROR, IO_ERROR, CHECKSUM_MISMATCH, NOT_FOUND, PERMISSION_DENIED, CANCELLED, UNKNOWN).
- For transient errors (TRANSPORT_ERROR), implement exponential backoff with jitter. Fail-fast on AUTH_ERROR/CREDENTIALS.

Performance Requirements
------------------------
- Size scans must be streamable: avoid reading full file contents; compute sizes via metadata where available. Provide cancellable scans via coroutine cancellation.
- Copy throughput: allow reporting of bytes/sec and duration; support pausing/resuming large file transfers.
- Migration should be able to resume within 5s of restart using last checkpoint.

Security
--------
- Credentials for cloud adapters must be stored encrypted (use or extend `SecurePreferencesManager`).
- Avoid logging sensitive tokens; anonymize URIs in logs.
- Request minimal permissions (SAF when possible) and present clear rationale to the user.

Hilt & DI
---------
- Provide a `SyncModule` that binds `SyncRepository` -> `SyncRepositoryImpl`, `CloudAdapter` factory, `SyncMigrationManager`, and helpers. Use `@Singleton` where appropriate.

Testing
-------
- Unit tests for:
  - `ExternalStorageHelper` size scan and cancellation.
  - `SyncRepositoryImpl.copyWithTiming` and `deleteWithTiming` with temp files.
  - `SyncMigrationManager` resume from checkpoint and checksum verification.
- Integration tests that run on CI emulators using `robolectric`/`androidTest` for SAF flows.

Migration UX Considerations
--------------------------
- Offer a dry-run mode showing estimated time and required free space.
- Provide pause/resume and show per-file ETA during migration.
- Warn users about risks and require confirmation for destructive ops (delete-on-target options).

Logging & Observability
-----------------------
- Emit structured logs for major events (migration_start, migration_checkpoint, migration_complete, metric_snapshot) to the existing `Logger`.
- Optionally expose metrics to remote telemetry when user opts-in.

Acceptance Criteria
-------------------
- Users can pick local/external/cloud target and start migration.
- Migrations are resumable after process kill.
- Metrics update in UI within 10s of worker run.
- No sensitive tokens are written to plain text logs.
- Automated tests cover critical migration code paths.

Next steps
----------
1. Implement `SyncRepositoryImpl` core primitives (copyWithTiming, deleteWithTiming, listFiles, validateFolderUri).
2. Implement `ExternalStorageHelper` and SAF integration.
3. Implement `CloudAdapter` (WebDAV adapter first).
4. Implement `SyncMigrationManager` and wire to ViewModel + Worker + Notifications.


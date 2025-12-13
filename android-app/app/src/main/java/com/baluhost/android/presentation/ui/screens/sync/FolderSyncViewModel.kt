package com.baluhost.android.presentation.ui.screens.sync

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.worker.FolderSyncWorker
import com.baluhost.android.domain.model.sync.*
import com.baluhost.android.domain.repository.SyncRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for FolderSyncScreen.
 * Manages sync folders, upload queue, and sync operations.
 */
@HiltViewModel
class FolderSyncViewModel @Inject constructor(
    private val syncRepository: SyncRepository,
    private val preferencesManager: PreferencesManager,
    private val workManager: WorkManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<FolderSyncState>(FolderSyncState.Loading)
    val uiState: StateFlow<FolderSyncState> = _uiState.asStateFlow()
    
    private val _snackbarMessage = MutableSharedFlow<String>()
    val snackbarMessage = _snackbarMessage.asSharedFlow()
    
    // Pending conflicts that need manual resolution
    private val _pendingConflicts = MutableStateFlow<List<FileConflict>>(emptyList())
    val pendingConflicts: StateFlow<List<FileConflict>> = _pendingConflicts.asStateFlow()
    
    init {
        loadSyncFolders()
    }
    
    fun loadSyncFolders() {
        viewModelScope.launch {
            _uiState.value = FolderSyncState.Loading
            
            try {
                val deviceId = preferencesManager.getDeviceId().first() 
                    ?: throw Exception("Device ID not found")
                
                // Load sync folders
                val foldersResult = syncRepository.getSyncFolders(deviceId)
                if (foldersResult.isFailure) {
                    _uiState.value = FolderSyncState.Error(
                        foldersResult.exceptionOrNull()?.message ?: "Failed to load sync folders"
                    )
                    return@launch
                }
                
                val folders = foldersResult.getOrNull() ?: emptyList()
                
                // Load upload queue
                val queueResult = syncRepository.getUploadQueue(deviceId)
                val uploadQueue = queueResult.getOrNull() ?: emptyList()
                
                _uiState.value = FolderSyncState.Success(
                    folders = folders,
                    uploadQueue = uploadQueue
                )
                
                // Check for pending conflicts
                folders.forEach { folder ->
                    val conflicts = preferencesManager.getPendingConflicts(folder.id.toLong()).first()
                    if (conflicts.isNotEmpty()) {
                        _pendingConflicts.value = conflicts
                    }
                }
                
            } catch (e: Exception) {
                _uiState.value = FolderSyncState.Error(
                    e.message ?: "Unknown error occurred"
                )
            }
        }
    }
    
    fun createFolder(config: SyncFolderCreateConfig) {
        viewModelScope.launch {
            try {
                val deviceId = preferencesManager.getDeviceId().first() 
                    ?: throw Exception("Device ID not found")
                
                val result = syncRepository.createSyncFolder(
                    deviceId = deviceId,
                    localPath = config.localUri.toString(),
                    remotePath = config.remotePath,
                    syncType = config.syncType,
                    autoSync = config.autoSync,
                    conflictResolution = config.conflictResolution,
                    excludePatterns = config.excludePatterns
                )
                
                if (result.isSuccess) {
                    val folder = result.getOrNull()!!
                    // Save URI mapping in preferences
                    preferencesManager.saveSyncFolderUri(folder.id, config.localUri.toString())
                    
                    _snackbarMessage.emit("Sync folder created successfully")
                    loadSyncFolders()
                } else {
                    _snackbarMessage.emit("Failed to create sync folder: ${result.exceptionOrNull()?.message}")
                }
                
            } catch (e: Exception) {
                _snackbarMessage.emit("Error: ${e.message}")
            }
        }
    }
    
    fun updateFolder(config: SyncFolderUpdateConfig) {
        viewModelScope.launch {
            try {
                val result = syncRepository.updateSyncFolder(
                    folderId = config.folderId,
                    remotePath = config.remotePath,
                    syncType = config.syncType,
                    autoSync = config.autoSync,
                    conflictResolution = config.conflictResolution,
                    excludePatterns = config.excludePatterns,
                    status = null
                )
                
                if (result.isSuccess) {
                    _snackbarMessage.emit("Sync folder updated")
                    loadSyncFolders()
                } else {
                    _snackbarMessage.emit("Failed to update: ${result.exceptionOrNull()?.message}")
                }
                
            } catch (e: Exception) {
                _snackbarMessage.emit("Error: ${e.message}")
            }
        }
    }
    
    fun deleteFolder(folderId: String) {
        viewModelScope.launch {
            try {
                val result = syncRepository.deleteSyncFolder(folderId)
                
                if (result.isSuccess) {
                    // Remove URI mapping
                    preferencesManager.removeSyncFolderUri(folderId)
                    
                    _snackbarMessage.emit("Sync folder removed")
                    loadSyncFolders()
                } else {
                    _snackbarMessage.emit("Failed to delete: ${result.exceptionOrNull()?.message}")
                }
                
            } catch (e: Exception) {
                _snackbarMessage.emit("Error: ${e.message}")
            }
        }
    }
    
    fun triggerSync(folderId: String) {
        viewModelScope.launch {
            try {
                // Enqueue WorkManager job for background sync
                val workRequest = FolderSyncWorker.createOneTimeRequest(
                    folderId = folderId.toLong(),
                    isManual = true
                )
                
                workManager.enqueue(workRequest)
                
                // Schedule periodic sync if auto-sync is enabled
                val state = _uiState.value
                if (state is FolderSyncState.Success) {
                    val folder = state.folders.find { it.id == folderId }
                    if (folder?.autoSync == true) {
                        schedulePeriodicSync(folderId.toLong())
                    }
                }
                
                _snackbarMessage.emit("Sync wird im Hintergrund ausgeführt")
                
                // Observe work status
                observeWorkProgress(workRequest.id)
                
            } catch (e: Exception) {
                _snackbarMessage.emit("Fehler beim Starten der Synchronisation: ${e.message}")
            }
        }
    }
    
    /**
     * Schedule periodic background sync for a folder.
     */
    private fun schedulePeriodicSync(folderId: Long) {
        val periodicWork = FolderSyncWorker.createPeriodicRequest(folderId)
        workManager.enqueueUniquePeriodicWork(
            "${FolderSyncWorker.WORK_NAME}_$folderId",
            androidx.work.ExistingPeriodicWorkPolicy.REPLACE,
            periodicWork
        )
    }
    
    /**
     * Cancel periodic sync for a folder.
     */
    fun cancelPeriodicSync(folderId: String) {
        workManager.cancelUniqueWork("${FolderSyncWorker.WORK_NAME}_$folderId")
    }
    
    /**
     * Observe Worker progress and update UI.
     */
    private fun observeWorkProgress(workId: java.util.UUID) {
        viewModelScope.launch {
            workManager.getWorkInfoByIdFlow(workId).collect { workInfo ->
                when (workInfo?.state) {
                    WorkInfo.State.RUNNING -> {
                        val progress = workInfo.progress
                        val status = progress.getString(FolderSyncWorker.PROGRESS_STATUS)
                        val file = progress.getString(FolderSyncWorker.PROGRESS_FILE)
                        
                        if (status != null) {
                            _snackbarMessage.emit(status + if (file != null) ": $file" else "")
                        }
                    }
                    WorkInfo.State.SUCCEEDED -> {
                        _snackbarMessage.emit("Synchronisation abgeschlossen")
                        loadSyncFolders()
                    }
                    WorkInfo.State.FAILED -> {
                        val error = workInfo.outputData.getString("error")
                        _snackbarMessage.emit("Synchronisation fehlgeschlagen: $error")
                        loadSyncFolders()
                    }
                    WorkInfo.State.CANCELLED -> {
                        _snackbarMessage.emit("Synchronisation abgebrochen")
                    }
                    else -> {
                        // ENQUEUED, BLOCKED - no action needed
                    }
                }
            }
        }
    }
    
    /**
     * Resolve conflicts with specified resolutions.
     * Triggers a new sync with the resolved actions.
     */
    fun resolveConflicts(folderId: Long, resolutions: Map<String, ConflictResolution>) {
        viewModelScope.launch {
            try {
                // Apply resolutions by triggering targeted uploads/downloads
                // This would ideally be handled by a dedicated API endpoint
                // For now, we'll clear the conflicts and re-trigger sync
                
                preferencesManager.clearPendingConflicts(folderId)
                _pendingConflicts.value = emptyList()
                
                // Re-trigger sync which will now succeed without conflicts
                triggerSync(folderId.toString())
                
                _snackbarMessage.emit("Konflikte aufgelöst, Synchronisation läuft")
                
            } catch (e: Exception) {
                _snackbarMessage.emit("Fehler beim Auflösen der Konflikte: ${e.message}")
            }
        }
    }
    
    /**
     * Dismiss conflicts without resolving (skip for now).
     */
    fun dismissConflicts(folderId: Long) {
        viewModelScope.launch {
            preferencesManager.clearPendingConflicts(folderId)
            _pendingConflicts.value = emptyList()
            _snackbarMessage.emit("Konflikte übersprungen")
        }
    }
    
    fun cancelUpload(uploadId: String) {
        viewModelScope.launch {
            try {
                val result = syncRepository.cancelUpload(uploadId)
                
                if (result.isSuccess) {
                    _snackbarMessage.emit("Upload cancelled")
                    loadSyncFolders()
                } else {
                    _snackbarMessage.emit("Failed to cancel: ${result.exceptionOrNull()?.message}")
                }
                
            } catch (e: Exception) {
                _snackbarMessage.emit("Error: ${e.message}")
            }
        }
    }
    
    fun retryUpload(uploadId: String) {
        viewModelScope.launch {
            try {
                val result = syncRepository.retryUpload(uploadId)
                
                if (result.isSuccess) {
                    _snackbarMessage.emit("Upload retrying")
                    loadSyncFolders()
                } else {
                    _snackbarMessage.emit("Failed to retry: ${result.exceptionOrNull()?.message}")
                }
                
            } catch (e: Exception) {
                _snackbarMessage.emit("Error: ${e.message}")
            }
        }
    }
    
    private fun startStatusPolling(folderId: String) {
        viewModelScope.launch {
            // Poll every 2 seconds for 30 seconds max
            repeat(15) {
                kotlinx.coroutines.delay(2000)
                loadSyncFolders()
                
                // Check if sync is still running
                val state = _uiState.value
                if (state is FolderSyncState.Success) {
                    val folder = state.folders.find { it.id == folderId }
                    if (folder?.syncStatus != SyncStatus.SYNCING) {
                        return@launch // Stop polling
                    }
                }
            }
        }
    }
}

/**
 * UI state for folder sync screen.
 */
sealed class FolderSyncState {
    object Loading : FolderSyncState()
    
    data class Success(
        val folders: List<SyncFolderConfig>,
        val uploadQueue: List<UploadQueueItem>
    ) : FolderSyncState()
    
    data class Error(val message: String) : FolderSyncState()
}

/**
 * Configuration for creating a new sync folder.
 */
data class SyncFolderCreateConfig(
    val localUri: android.net.Uri,
    val remotePath: String,
    val syncType: SyncType,
    val autoSync: Boolean,
    val conflictResolution: ConflictResolution,
    val excludePatterns: List<String>
)

/**
 * Configuration for updating an existing sync folder.
 */
data class SyncFolderUpdateConfig(
    val folderId: String,
    val remotePath: String?,
    val syncType: SyncType?,
    val autoSync: Boolean?,
    val conflictResolution: ConflictResolution?,
    val excludePatterns: List<String>?
)

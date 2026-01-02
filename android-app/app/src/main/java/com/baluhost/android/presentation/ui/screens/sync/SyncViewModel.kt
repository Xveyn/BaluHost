package com.baluhost.android.presentation.ui.screens.sync

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.model.sync.ConflictResolution
import com.baluhost.android.domain.model.sync.SyncFolderConfig
import com.baluhost.android.domain.model.sync.SyncStatus
import com.baluhost.android.domain.model.sync.SyncType
import com.baluhost.android.domain.repository.SyncRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class UiSyncFolder(
    val path: String,
    val displayName: String,
    val enabled: Boolean = false,
    val syncStatus: SyncStatus = SyncStatus.IDLE
)

data class SyncUiState(
    val folders: List<UiSyncFolder> = emptyList()
)

@HiltViewModel
class SyncViewModel @Inject constructor(
    private val syncRepository: SyncRepository,
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    private val _uiState = MutableStateFlow(SyncUiState())
    val uiState: StateFlow<SyncUiState> = _uiState.asStateFlow()

    init {
        // Load existing remote sync folders and seed local folder list
        viewModelScope.launch {
            com.baluhost.android.util.Logger.i("SyncViewModel", "init: loading sync folders")
            val deviceId = preferencesManager.getDeviceId().first() ?: ""
            val username = preferencesManager.getUsername().first() ?: "user"

            val remoteFoldersResult = runCatching { syncRepository.getSyncFolders(deviceId) }
            if (remoteFoldersResult.isFailure) {
                com.baluhost.android.util.Logger.e("SyncViewModel", "Failed fetching remote folders", remoteFoldersResult.exceptionOrNull())
            }
            val remoteFolders = remoteFoldersResult.getOrNull()?.getOrNull() ?: emptyList()

            // TODO: Replace sample local scan with SAF or storage scanning
            val local = listOf(
                UiSyncFolder(path = "/storage/emulated/0/DCIM", displayName = "DCIM"),
                UiSyncFolder(path = "/storage/emulated/0/Pictures", displayName = "Pictures"),
                UiSyncFolder(path = "/storage/emulated/0/Download", displayName = "Download")
            )

            // Mark enabled if a remote folder exists for this local path or displayName
            val annotated = local.map { lf ->
                val matched = remoteFolders.firstOrNull { rf ->
                    matchesLocalToRemote(lf.path, lf.displayName, rf)
                }
                if (matched != null) lf.copy(enabled = true, syncStatus = matched.syncStatus) else lf
            }

            _uiState.value = SyncUiState(folders = annotated)
            com.baluhost.android.util.Logger.i("SyncViewModel", "init: loaded ${annotated.size} local folders, remote matches ${remoteFolders.size}")
        }
    }

    private fun matchesLocalToRemote(localPath: String, displayName: String, remote: SyncFolderConfig): Boolean {
        // Try matching by localUri string or by remotePath containing the display name
        return try {
            (remote.localUri.toString() == localPath) || remote.remotePath.contains(displayName)
        } catch (e: Exception) {
            false
        }
    }

    fun toggleFolderEnabled(path: String) {
        viewModelScope.launch {
            val folder = _uiState.value.folders.firstOrNull { it.path == path } ?: return@launch

            // If enabling -> create remote folder under user's root
            if (!folder.enabled) {
                val deviceId = preferencesManager.getDeviceId().first() ?: ""
                val username = preferencesManager.getUsername().first() ?: "user"
                val remotePath = "${username}-root/${folder.displayName}"

                val result = syncRepository.createSyncFolder(
                    deviceId = deviceId,
                    localPath = folder.path,
                    remotePath = remotePath,
                    syncType = SyncType.BIDIRECTIONAL,
                    autoSync = true,
                    conflictResolution = ConflictResolution.KEEP_NEWEST,
                    excludePatterns = emptyList(),
                    adapterType = "webdav",
                    adapterUsername = null,
                    adapterPassword = null,
                    saveCredentials = false
                )

                if (result.isSuccess) {
                    val updated = _uiState.value.folders.map { f -> if (f.path == path) f.copy(enabled = true, syncStatus = result.getOrNull()?.syncStatus ?: SyncStatus.IDLE) else f }
                    _uiState.value = _uiState.value.copy(folders = updated)
                } else {
                    // mark error
                    val updated = _uiState.value.folders.map { f -> if (f.path == path) f.copy(syncStatus = SyncStatus.ERROR) else f }
                    _uiState.value = _uiState.value.copy(folders = updated)
                }
            } else {
                // disabling -> try to find remote folder and delete it
                val deviceId = preferencesManager.getDeviceId().first() ?: ""
                val remoteResult = syncRepository.getSyncFolders(deviceId)
                val remote = remoteResult.getOrNull()?.firstOrNull { rf -> matchesLocalToRemote(folder.path, folder.displayName, rf) }

                if (remote != null) {
                    val del = syncRepository.deleteSyncFolder(remote.id)
                    if (del.isSuccess) {
                        val updated = _uiState.value.folders.map { f -> if (f.path == path) f.copy(enabled = false, syncStatus = SyncStatus.IDLE) else f }
                        _uiState.value = _uiState.value.copy(folders = updated)
                    } else {
                        val updated = _uiState.value.folders.map { f -> if (f.path == path) f.copy(syncStatus = SyncStatus.ERROR) else f }
                        _uiState.value = _uiState.value.copy(folders = updated)
                    }
                } else {
                    // nothing on server, just disable locally
                    val updated = _uiState.value.folders.map { f -> if (f.path == path) f.copy(enabled = false) else f }
                    _uiState.value = _uiState.value.copy(folders = updated)
                }
            }
        }
    }
}

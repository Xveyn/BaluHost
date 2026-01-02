package com.baluhost.android.presentation.ui.screens.files

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.network.NetworkMonitor
import com.baluhost.android.data.network.ServerConnectivityChecker
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.domain.usecase.OfflineQueueManager
import com.baluhost.android.domain.usecase.files.DeleteFileUseCase
import com.baluhost.android.domain.usecase.files.DownloadFileUseCase
import com.baluhost.android.domain.usecase.files.GetFilesUseCase
import com.baluhost.android.domain.usecase.files.UploadFileUseCase
import com.baluhost.android.util.NetworkStateManager
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * ViewModel for Files Screen.
 * 
 * Manages file list and file operations (upload, download, delete).
 * Supports offline queue for failed operations.
 */
@HiltViewModel
class FilesViewModel @Inject constructor(
    private val getFilesUseCase: GetFilesUseCase,
    private val uploadFileUseCase: UploadFileUseCase,
    private val downloadFileUseCase: DownloadFileUseCase,
    private val deleteFileUseCase: DeleteFileUseCase,
    private val moveFileUseCase: com.baluhost.android.domain.usecase.files.MoveFileUseCase,
    private val preferencesManager: PreferencesManager,
    private val networkMonitor: NetworkMonitor,
    private val serverConnectivityChecker: ServerConnectivityChecker,
    private val offlineQueueManager: OfflineQueueManager,
    private val networkStateManager: NetworkStateManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(FilesUiState())
    val uiState: StateFlow<FilesUiState> = _uiState.asStateFlow()
    
    // VPN-related state flows
    private val _isInHomeNetwork = MutableStateFlow<Boolean?>(null)
    val isInHomeNetwork: StateFlow<Boolean?> = _isInHomeNetwork.asStateFlow()
    
    private val _hasVpnConfig = MutableStateFlow(false)
    val hasVpnConfig: StateFlow<Boolean> = _hasVpnConfig.asStateFlow()
    
    private val _vpnBannerDismissed = MutableStateFlow(false)
    val vpnBannerDismissed: StateFlow<Boolean> = _vpnBannerDismissed.asStateFlow()
    
    private val _isVpnActive = MutableStateFlow(false)
    val isVpnActive: StateFlow<Boolean> = _isVpnActive.asStateFlow()
    
    private val pathStack = mutableListOf<String>()
    
    private var wasOffline = false
    
    init {
        // Set initial online state - check both network AND server reachability
        val hasNetwork = networkMonitor.isCurrentlyOnline()
        val serverReachable = serverConnectivityChecker.isCurrentlyReachable()
        val initialOnlineState = hasNetwork && serverReachable
        
        android.util.Log.d("FilesViewModel", "Initial state - Network: $hasNetwork, Server: $serverReachable, Online: $initialOnlineState")
        _uiState.value = _uiState.value.copy(isOnline = initialOnlineState)
        
        // Trigger immediate server check on app start
        viewModelScope.launch {
            serverConnectivityChecker.checkServerConnectivity()
        }
        
        checkAuthenticationAndLoadFiles()
        observeNetworkStatus()
        observeServerConnectivity()
        observePendingOperationsCount()
        observeHomeNetworkState()
        checkVpnConfig()
    }
    
    /**
     * Observe network status changes (WiFi/Mobile data).
     * Combined with server connectivity for complete offline detection.
     */
    private fun observeNetworkStatus() {
        viewModelScope.launch {
            networkMonitor.isOnline.collect { hasNetwork ->
                android.util.Log.d("FilesViewModel", "Network status changed: $hasNetwork")
                
                // Update online state: requires both network AND server reachability
                val serverReachable = serverConnectivityChecker.isCurrentlyReachable()
                val isOnline = hasNetwork && serverReachable
                _uiState.value = _uiState.value.copy(isOnline = isOnline)
                
                // Auto-refresh when reconnecting
                if (isOnline && wasOffline) {
                    android.util.Log.d("FilesViewModel", "Connectivity restored, refreshing files")
                    refreshFiles()
                }
                
                wasOffline = !isOnline
            }
        }
    }
    
    /**
     * Observe server connectivity status (actual BaluHost server reachability).
     * This is more accurate than just network status.
     */
    private fun observeServerConnectivity() {
        viewModelScope.launch {
            serverConnectivityChecker.isServerReachable.collect { serverReachable ->
                android.util.Log.d("FilesViewModel", "Server reachability changed: $serverReachable")
                
                // Update online state: requires both network AND server reachability
                val hasNetwork = networkMonitor.isCurrentlyOnline()
                val isOnline = hasNetwork && serverReachable
                
                val wasOnline = _uiState.value.isOnline
                _uiState.value = _uiState.value.copy(isOnline = isOnline)
                
                // Auto-refresh when server becomes reachable
                if (isOnline && !wasOnline) {
                    android.util.Log.d("FilesViewModel", "Server became reachable, refreshing files")
                    refreshFiles()
                }
            }
        }
    }
    
    /**
     * Observe pending operations count for UI badge.
     */
    private fun observePendingOperationsCount() {
        viewModelScope.launch {
            offlineQueueManager.observePendingCount().collect { count ->
                _uiState.value = _uiState.value.copy(pendingOperationsCount = count)
            }
        }
    }
    
    /**
     * Observe home network status for VPN hint banner.
     * Checks if device is in same network as NAS server (same subnet).
     */
    private fun observeHomeNetworkState() {
        viewModelScope.launch {
            preferencesManager.getServerUrl().collectLatest { serverUrl ->
                if (serverUrl != null) {
                    networkStateManager.observeHomeNetworkStatus(serverUrl)
                        .collect { isHome -> 
                            _isInHomeNetwork.value = isHome
                                // update explicit vpn active flag from network manager
                                _isVpnActive.value = networkStateManager.isVpnActive()
                        }
                }
            }
        }
    }
    
    /**
     * Check if VPN config is available in preferences.
     */
    private fun checkVpnConfig() {
        viewModelScope.launch {
            preferencesManager.getVpnConfig().collect { config ->
                _hasVpnConfig.value = !config.isNullOrEmpty()
            }
        }
    }
    
    /**
     * Dismiss VPN hint banner.
     */
    fun dismissVpnBanner() {
        _vpnBannerDismissed.value = true
    }
    
    private fun checkAuthenticationAndLoadFiles() {
        viewModelScope.launch {
            // Check if device is registered
            val deviceId = preferencesManager.getDeviceId().first()
            val accessToken = preferencesManager.getAccessToken().first()
            
            if (deviceId == null || accessToken == null) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = "Gerät ist nicht registriert. Bitte scannen Sie den QR-Code."
                )
                return@launch
            }
            
            loadFiles()
        }
    }
    
    /**
     * Called when app resumes (e.g., after unlock).
     * Triggers immediate server connectivity check.
     */
    fun onAppResume() {
        viewModelScope.launch {
            android.util.Log.d("FilesViewModel", "App resumed - checking server connectivity")
            val isReachable = serverConnectivityChecker.forceCheckAndWait()
            android.util.Log.d("FilesViewModel", "Server reachable after resume: $isReachable")
            
            if (isReachable) {
                // Refresh file list if server is reachable
                refreshFiles()
            }
        }
    }
    
    fun loadFiles(path: String = "") {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            
            val result = getFilesUseCase(path, forceRefresh = false)
            
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        files = result.data,
                        currentPath = path,
                        isLoading = false,
                        error = null  // Clear any previous errors
                    )
                }
                is Result.Error -> {
                    // Check if we have cached data
                    val hasCachedData = _uiState.value.files.isNotEmpty()
                    
                    // Show friendly error message based on network status
                    val errorMsg = when {
                        !networkMonitor.isCurrentlyOnline() && hasCachedData -> 
                            "Offline - Zeige gecachte Dateien"
                        !networkMonitor.isCurrentlyOnline() && !hasCachedData -> 
                            "Keine Verbindung zum Server"
                        !serverConnectivityChecker.isCurrentlyReachable() && hasCachedData ->
                            "Server nicht erreichbar - Zeige gecachte Dateien"
                        !serverConnectivityChecker.isCurrentlyReachable() && !hasCachedData ->
                            "Server nicht erreichbar"
                        else -> result.exception.message
                    }
                    
                    // Mark as offline if server is not reachable (connection error)
                    val isConnectionError = result.exception.message?.contains("Failed to connect", ignoreCase = true) == true ||
                                           result.exception.message?.contains("timeout", ignoreCase = true) == true ||
                                           result.exception.message?.contains("refused", ignoreCase = true) == true
                    
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        currentPath = path,
                        error = errorMsg,
                        isOnline = if (isConnectionError) false else _uiState.value.isOnline
                    )
                }
                is Result.Loading -> {
                    // Already loading
                }
            }
        }
    }
    
    /**
     * Force refresh from network (for pull-to-refresh).
     * Uses cache-first but forces network fetch even if cache is fresh.
     */
    fun refreshFiles() {
        viewModelScope.launch {
            // Check if server is reachable before trying to refresh
            val hasNetwork = networkMonitor.isCurrentlyOnline()
            val serverReachable = serverConnectivityChecker.isCurrentlyReachable()
            
            if (!hasNetwork || !serverReachable) {
                val errorMsg = when {
                    !hasNetwork -> "Keine Netzwerkverbindung"
                    !serverReachable -> "Server nicht erreichbar"
                    else -> "Keine Verbindung"
                }
                
                _uiState.value = _uiState.value.copy(
                    isRefreshing = false,
                    error = "$errorMsg - Kann nicht aktualisieren"
                )
                return@launch
            }
            
            _uiState.value = _uiState.value.copy(isRefreshing = true, error = null)
            
            val result = getFilesUseCase(_uiState.value.currentPath, forceRefresh = true)
            
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        files = result.data,
                        isRefreshing = false,
                        error = null
                    )
                }
                is Result.Error -> {
                    val errorMsg = if (!networkMonitor.isCurrentlyOnline()) {
                        "Verbindung verloren während Aktualisierung"
                    } else {
                        "Aktualisierung fehlgeschlagen: ${result.exception.message}"
                    }
                    
                    // Mark as offline if server is not reachable
                    val isConnectionError = result.exception.message?.contains("Failed to connect", ignoreCase = true) == true ||
                                           result.exception.message?.contains("timeout", ignoreCase = true) == true ||
                                           result.exception.message?.contains("refused", ignoreCase = true) == true
                    
                    _uiState.value = _uiState.value.copy(
                        isRefreshing = false,
                        error = errorMsg,
                        isOnline = if (isConnectionError) false else _uiState.value.isOnline
                    )
                }
                is Result.Loading -> {
                    // Already refreshing
                }
            }
        }
    }
    
    fun navigateToFolder(folderName: String) {
        val newPath = if (_uiState.value.currentPath.isEmpty()) {
            folderName
        } else {
            "${_uiState.value.currentPath}/$folderName"
        }
        
        pathStack.add(_uiState.value.currentPath)
        loadFiles(newPath)
    }
    
    fun navigateBack(): Boolean {
        if (pathStack.isEmpty()) {
            return false // At root, can't go back
        }
        
        val previousPath = pathStack.removeLastOrNull() ?: ""
        loadFiles(previousPath)
        return true
    }
    
    fun uploadFile(file: File, destinationPath: String? = null) {
        viewModelScope.launch {
            val uploadPath = destinationPath ?: _uiState.value.currentPath
            
            // Check network connectivity
            if (!networkMonitor.isCurrentlyOnline()) {
                // Queue for later when online
                android.util.Log.d("FilesViewModel", "Offline, queueing upload: ${file.name}")
                when (val result = offlineQueueManager.queueUpload(file, uploadPath)) {
                    is Result.Success -> {
                        _uiState.value = _uiState.value.copy(
                            error = "Keine Verbindung. Upload wird automatisch wiederholt wenn online."
                        )
                    }
                    is Result.Error -> {
                        _uiState.value = _uiState.value.copy(
                            error = "Fehler beim Queuen des Uploads: ${result.exception.message}"
                        )
                    }
                    is Result.Loading -> {
                        // Queuing in progress
                    }
                }
                return@launch
            }
            
            _uiState.value = _uiState.value.copy(
                uploadProgress = 0f,
                isUploading = true,
                error = null
            )
            
            val result = uploadFileUseCase(file, uploadPath)
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        isUploading = false,
                        uploadProgress = 0f
                    )
                    loadFiles(_uiState.value.currentPath) // Refresh list
                }
                is Result.Error -> {
                    // Queue for retry
                    android.util.Log.d("FilesViewModel", "Upload failed, queueing for retry: ${result.exception.message}")
                    offlineQueueManager.queueUpload(file, uploadPath)
                    
                    _uiState.value = _uiState.value.copy(
                        isUploading = false,
                        uploadProgress = 0f,
                        error = "Upload fehlgeschlagen. Wird automatisch wiederholt: ${result.exception.message}"
                    )
                }
                is Result.Loading -> {
                    // Upload in progress
                }
            }
        }
    }
    
    fun downloadFile(filePath: String, destinationFile: File) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                downloadProgress = 0f,
                isDownloading = true,
                error = null
            )
            
            val result = downloadFileUseCase(filePath, destinationFile)
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        isDownloading = false,
                        downloadProgress = 0f
                    )
                }
                is Result.Error -> {
                    _uiState.value = _uiState.value.copy(
                        isDownloading = false,
                        downloadProgress = 0f,
                        error = result.exception.message
                    )
                }
                is Result.Loading -> {
                    // Download in progress
                }
            }
        }
    }
    
    /**
     * Get download URL for a file to open in media viewer.
     */
    fun getFileDownloadUrl(filePath: String): String {
        // Get server URL from preferences - use runBlocking since we need it synchronously
        val serverUrl = kotlinx.coroutines.runBlocking {
            preferencesManager.getServerUrl().first()
        } ?: "http://192.168.178.21:8000" // Fallback to default
        
        // Remove trailing slash if present
        val baseUrl = serverUrl.trimEnd('/')
        
        // URL encode the file path
        val encodedPath = java.net.URLEncoder.encode(filePath, "UTF-8")
        
        android.util.Log.d("FilesViewModel", "Download URL: $baseUrl/api/files/download/$encodedPath")
        return "$baseUrl/api/files/download/$encodedPath"
    }
    
    fun deleteFile(filePath: String) {
        viewModelScope.launch {
            android.util.Log.d("FilesViewModel", "Deleting file: $filePath")
            _uiState.value = _uiState.value.copy(error = null)
            
            // Check network connectivity
            if (!networkMonitor.isCurrentlyOnline()) {
                // Queue for later when online
                android.util.Log.d("FilesViewModel", "Offline, queueing delete: $filePath")
                when (val result = offlineQueueManager.queueDelete(filePath)) {
                    is Result.Success -> {
                        _uiState.value = _uiState.value.copy(
                            error = "Keine Verbindung. Löschung wird automatisch wiederholt wenn online."
                        )
                        // Optimistically remove from UI
                        val updatedFiles = _uiState.value.files.filter { it.path != filePath }
                        _uiState.value = _uiState.value.copy(files = updatedFiles)
                    }
                    is Result.Error -> {
    
    /**
     * Called when app resumes from background.
     * Triggers immediate server connectivity check.
     */
    fun onAppResume() {
        android.util.Log.d("FilesViewModel", "App resumed, checking server connectivity")
        viewModelScope.launch {
            // Force immediate server check
            val isReachable = serverConnectivityChecker.forceCheckAndWait()
            android.util.Log.d("FilesViewModel", "Server check after resume: $isReachable")
            
            // Refresh files if server is reachable
            if (isReachable) {
                refreshFiles()
            }
        }
    }
                        _uiState.value = _uiState.value.copy(
                            error = "Fehler beim Queuen der Löschung: ${result.exception.message}"
                        )
                    }
                    is Result.Loading -> {
                        // Queuing in progress
                    }
                }
                return@launch
            }
            
            val result = deleteFileUseCase(filePath)
            
            when (result) {
                is Result.Success -> {
                    android.util.Log.d("FilesViewModel", "Delete successful, refreshing list")
                    loadFiles(_uiState.value.currentPath) // Refresh list
                }
                is Result.Error -> {
                    android.util.Log.e("FilesViewModel", "Delete failed: ${result.exception.message}")
                    
                    // Queue for retry
                    offlineQueueManager.queueDelete(filePath)
                    
                    _uiState.value = _uiState.value.copy(
                        error = "Löschung fehlgeschlagen. Wird automatisch wiederholt: ${result.exception.message}"
                    )
                }
                is Result.Loading -> {
                    // Delete in progress
                }
            }
        }
    }
    
    fun clearError() {
        _uiState.value = _uiState.value.copy(error = null)
    }
    
    // ==================== Batch Operations ====================
    
    /**
     * Toggle selection mode (multi-select).
     */
    fun toggleSelectionMode() {
        val newMode = !_uiState.value.isSelectionMode
        _uiState.value = _uiState.value.copy(
            isSelectionMode = newMode,
            selectedFiles = if (!newMode) emptySet() else _uiState.value.selectedFiles
        )
    }
    
    /**
     * Toggle selection for a single file.
     */
    fun toggleFileSelection(file: FileItem) {
        val currentSelection = _uiState.value.selectedFiles
        val newSelection = if (file in currentSelection) {
            currentSelection - file
        } else {
            currentSelection + file
        }
        _uiState.value = _uiState.value.copy(selectedFiles = newSelection)
    }
    
    /**
     * Select all files in current directory.
     */
    fun selectAll() {
        _uiState.value = _uiState.value.copy(
            selectedFiles = _uiState.value.files.toSet()
        )
    }
    
    /**
     * Deselect all files.
     */
    fun deselectAll() {
        _uiState.value = _uiState.value.copy(selectedFiles = emptySet())
    }
    
    /**
     * Delete selected files in batch.
     */
    fun deleteSelectedFiles() {
        val filesToDelete = _uiState.value.selectedFiles
        if (filesToDelete.isEmpty()) return
        
        viewModelScope.launch {
            android.util.Log.d("FilesViewModel", "Batch deleting ${filesToDelete.size} files")
            
            var successCount = 0
            var failCount = 0
            
            filesToDelete.forEach { file ->
                when (val result = deleteFileUseCase(file.path)) {
                    is Result.Success -> {
                        successCount++
                    }
                    is Result.Error -> {
                        failCount++
                        // Queue for retry
                        offlineQueueManager.queueDelete(file.path)
                    }
                    is Result.Loading -> {}
                }
            }
            
            // Clear selection and exit selection mode
            _uiState.value = _uiState.value.copy(
                isSelectionMode = false,
                selectedFiles = emptySet(),
                error = if (failCount > 0) {
                    "$successCount gelöscht, $failCount fehlgeschlagen (werden wiederholt)"
                } else {
                    null
                }
            )
            
            // Refresh file list
            refreshFiles()
        }
    }
    
    /**
     * Download selected files in batch.
     */
    fun downloadSelectedFiles() {
        val filesToDownload = _uiState.value.selectedFiles.filter { !it.isDirectory }
        if (filesToDownload.isEmpty()) {
            _uiState.value = _uiState.value.copy(
                error = "Keine Dateien ausgewählt (Ordner können nicht heruntergeladen werden)"
            )
            return
        }
        
        viewModelScope.launch {
            android.util.Log.d("FilesViewModel", "Batch downloading ${filesToDownload.size} files")
            
            var successCount = 0
            var failCount = 0
            
            filesToDownload.forEach { file ->
                // Create temporary download destination
                val tempFile = java.io.File.createTempFile("download_", "_${file.name}")
                when (downloadFileUseCase(file.path, tempFile)) {
                    is Result.Success -> successCount++
                    is Result.Error -> failCount++
                    is Result.Loading -> {}
                }
            }
            
            _uiState.value = _uiState.value.copy(
                isSelectionMode = false,
                selectedFiles = emptySet(),
                error = if (failCount > 0) {
                    "$successCount heruntergeladen, $failCount fehlgeschlagen"
                } else null
            )
        }
    }
    
    /**
     * Move selected files to destination folder.
     */
    fun moveSelectedFiles(destinationPath: String) {
        val filesToMove = _uiState.value.selectedFiles
        if (filesToMove.isEmpty()) {
            _uiState.value = _uiState.value.copy(error = "Keine Dateien ausgewählt")
            return
        }
        
        viewModelScope.launch {
            android.util.Log.d("FilesViewModel", "Batch moving ${filesToMove.size} files to $destinationPath")
            
            var successCount = 0
            var failCount = 0
            
            filesToMove.forEach { file ->
                val destPath = if (destinationPath.isEmpty() || destinationPath == "/") {
                    "/${file.name}"
                } else {
                    "$destinationPath/${file.name}"
                }
                
                when (moveFileUseCase(file.path, destPath)) {
                    is Result.Success -> successCount++
                    is Result.Error -> {
                        failCount++
                        // Queue for offline retry
                        offlineQueueManager.queueMove(file.path, destPath)
                    }
                    is Result.Loading -> {}
                }
            }
            
            _uiState.value = _uiState.value.copy(
                isSelectionMode = false,
                selectedFiles = emptySet(),
                error = if (failCount > 0) {
                    "$successCount verschoben, $failCount fehlgeschlagen"
                } else null
            )
            
            // Refresh file list
            refreshFiles()
        }
    }
}

data class FilesUiState(
    val files: List<FileItem> = emptyList(),
    val currentPath: String = "",
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,  // For pull-to-refresh
    val isUploading: Boolean = false,
    val isDownloading: Boolean = false,
    val uploadProgress: Float = 0f,
    val downloadProgress: Float = 0f,
    val error: String? = null,
    val isOnline: Boolean = false,  // Default offline, updated in init
    val pendingOperationsCount: Int = 0,  // Count of queued operations
    
    // Batch Operations
    val isSelectionMode: Boolean = false,  // Multi-select mode active
    val selectedFiles: Set<FileItem> = emptySet()  // Selected files for batch operations
)

package com.baluhost.android.presentation.ui.screens.files

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.domain.usecase.files.DeleteFileUseCase
import com.baluhost.android.domain.usecase.files.DownloadFileUseCase
import com.baluhost.android.domain.usecase.files.GetFilesUseCase
import com.baluhost.android.domain.usecase.files.UploadFileUseCase
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * ViewModel for Files Screen.
 * 
 * Manages file list and file operations (upload, download, delete).
 */
@HiltViewModel
class FilesViewModel @Inject constructor(
    private val getFilesUseCase: GetFilesUseCase,
    private val uploadFileUseCase: UploadFileUseCase,
    private val downloadFileUseCase: DownloadFileUseCase,
    private val deleteFileUseCase: DeleteFileUseCase,
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(FilesUiState())
    val uiState: StateFlow<FilesUiState> = _uiState.asStateFlow()
    
    private val pathStack = mutableListOf<String>()
    
    init {
        checkAuthenticationAndLoadFiles()
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
    
    fun loadFiles(path: String = "") {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            
            val result = getFilesUseCase(path, forceRefresh = false)
            
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        files = result.data,
                        currentPath = path,
                        isLoading = false
                    )
                }
                is Result.Error -> {
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = result.exception.message
                    )
                }
                else -> {
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = "Unknown error"
                    )
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
            _uiState.value = _uiState.value.copy(isRefreshing = true, error = null)
            
            val result = getFilesUseCase(_uiState.value.currentPath, forceRefresh = true)
            
            when (result) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        files = result.data,
                        isRefreshing = false
                    )
                }
                is Result.Error -> {
                    _uiState.value = _uiState.value.copy(
                        isRefreshing = false,
                        error = result.exception.message
                    )
                }
                else -> {
                    _uiState.value = _uiState.value.copy(
                        isRefreshing = false,
                        error = "Unknown error"
                    )
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
                    _uiState.value = _uiState.value.copy(
                        isUploading = false,
                        uploadProgress = 0f,
                        error = result.exception.message
                    )
                }
                else -> {
                    _uiState.value = _uiState.value.copy(
                        isUploading = false,
                        uploadProgress = 0f,
                        error = "Unknown error"
                    )
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
                else -> {
                    _uiState.value = _uiState.value.copy(
                        isDownloading = false,
                        downloadProgress = 0f,
                        error = "Unknown error"
                    )
                }
            }
        }
    }
    
    /**
     * Get download URL for a file to open in media viewer.
     */
    fun getFileDownloadUrl(filePath: String): String {
        // TODO: Get base URL from preferences/config
        val baseUrl = "http://192.168.178.21:8000" // Replace with actual server URL
        return "$baseUrl/api/files/download/$filePath"
    }
    
    fun deleteFile(filePath: String) {
        viewModelScope.launch {
            android.util.Log.d("FilesViewModel", "Deleting file: $filePath")
            _uiState.value = _uiState.value.copy(error = null)
            
            val result = deleteFileUseCase(filePath)
            
            when (result) {
                is Result.Success -> {
                    android.util.Log.d("FilesViewModel", "Delete successful, refreshing list")
                    loadFiles(_uiState.value.currentPath) // Refresh list
                }
                is Result.Error -> {
                    android.util.Log.e("FilesViewModel", "Delete failed: ${result.exception.message}")
                    _uiState.value = _uiState.value.copy(
                        error = result.exception.message
                    )
                }
                else -> {
                    android.util.Log.e("FilesViewModel", "Delete unknown error")
                    _uiState.value = _uiState.value.copy(
                        error = "Unknown error"
                    )
                }
            }
        }
    }
    
    fun clearError() {
        _uiState.value = _uiState.value.copy(error = null)
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
    val error: String? = null
)

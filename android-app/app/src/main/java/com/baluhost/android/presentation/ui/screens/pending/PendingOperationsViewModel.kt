package com.baluhost.android.presentation.ui.screens.pending

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.domain.model.PendingOperation
import com.baluhost.android.domain.usecase.OfflineQueueManager
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Pending Operations Screen.
 */
@HiltViewModel
class PendingOperationsViewModel @Inject constructor(
    private val offlineQueueManager: OfflineQueueManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(PendingOperationsUiState())
    val uiState: StateFlow<PendingOperationsUiState> = _uiState.asStateFlow()
    
    init {
        observePendingOperations()
    }
    
    private fun observePendingOperations() {
        viewModelScope.launch {
            offlineQueueManager.observePendingOperations().collect { operations ->
                _uiState.value = _uiState.value.copy(
                    operations = operations,
                    isLoading = false
                )
            }
        }
    }
    
    fun retryOperation(operationId: Long) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            
            val operation = _uiState.value.operations.find { it.id == operationId }
            if (operation != null) {
                offlineQueueManager.retryOperation(operation)
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    message = "Operation wird wiederholt..."
                )
            }
        }
    }
    
    fun cancelOperation(operationId: Long) {
        viewModelScope.launch {
            when (val result = offlineQueueManager.cancelOperation(operationId)) {
                is Result.Success -> {
                    _uiState.value = _uiState.value.copy(
                        message = "Operation abgebrochen"
                    )
                }
                is Result.Error -> {
                    _uiState.value = _uiState.value.copy(
                        message = "Fehler beim Abbrechen: ${result.exception.message}"
                    )
                }
                is Result.Loading -> {}
            }
        }
    }
    
    fun clearMessage() {
        _uiState.value = _uiState.value.copy(message = null)
    }
}

data class PendingOperationsUiState(
    val operations: List<PendingOperation> = emptyList(),
    val isLoading: Boolean = true,
    val message: String? = null
)

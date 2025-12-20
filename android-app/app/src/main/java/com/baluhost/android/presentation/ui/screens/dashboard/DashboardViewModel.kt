package com.baluhost.android.presentation.ui.screens.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import android.util.Log
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.domain.model.RaidArray
import com.baluhost.android.domain.model.SystemInfo
import com.baluhost.android.domain.usecase.cache.GetCacheStatsUseCase
import com.baluhost.android.domain.usecase.files.GetFilesUseCase
import com.baluhost.android.domain.usecase.system.GetRaidStatusUseCase
import com.baluhost.android.domain.usecase.system.GetSystemTelemetryUseCase
import com.baluhost.android.util.NetworkStateManager
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Dashboard screen.
 */
@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val getFilesUseCase: GetFilesUseCase,
    private val getCacheStatsUseCase: GetCacheStatsUseCase,
    private val getSystemTelemetryUseCase: GetSystemTelemetryUseCase,
    private val getRaidStatusUseCase: GetRaidStatusUseCase,
    private val preferencesManager: PreferencesManager,
    private val networkStateManager: NetworkStateManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(DashboardUiState())
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()
    
    // VPN-related state flows
    private val _isInHomeNetwork = MutableStateFlow<Boolean?>(null)
    val isInHomeNetwork: StateFlow<Boolean?> = _isInHomeNetwork.asStateFlow()
    
    private val _hasVpnConfig = MutableStateFlow(false)
    val hasVpnConfig: StateFlow<Boolean> = _hasVpnConfig.asStateFlow()
    
    private val _vpnBannerDismissed = MutableStateFlow(false)
    val vpnBannerDismissed: StateFlow<Boolean> = _vpnBannerDismissed.asStateFlow()
    
    private var pollingJob: kotlinx.coroutines.Job? = null
    
    init {
        loadDashboardData()
        startPolling()
        observeHomeNetworkState()
        checkVpnConfig()
    }
    
    override fun onCleared() {
        super.onCleared()
        pollingJob?.cancel()
    }
    
    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
            while (true) {
                kotlinx.coroutines.delay(30_000) // 30 seconds
                loadTelemetryData()
            }
        }
    }
    
    private fun loadDashboardData() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            
            try {
                // Load username
                val username = preferencesManager.getUsername().first() ?: "User"
                
                // Load system telemetry
                val telemetryResult = getSystemTelemetryUseCase()
                val telemetry = when (telemetryResult) {
                    is Result.Success -> {
                        Log.d("DashboardViewModel", "Telemetry loaded: CPU=${telemetryResult.data.cpu.usagePercent}%, Memory=${telemetryResult.data.memory.usagePercent}%, Disk=${telemetryResult.data.disk.usagePercent}%")
                        telemetryResult.data
                    }
                    is Result.Error -> {
                        Log.e("DashboardViewModel", "Failed to load telemetry", telemetryResult.exception)
                        null
                    }
                    else -> null
                }
                
                // Load RAID status
                val raidResult = getRaidStatusUseCase()
                val raidArrays = when (raidResult) {
                    is Result.Success -> {
                        Log.d("DashboardViewModel", "RAID arrays loaded: ${raidResult.data.size} arrays")
                        raidResult.data
                    }
                    is Result.Error -> {
                        Log.e("DashboardViewModel", "Failed to load RAID status", raidResult.exception)
                        emptyList()
                    }
                    else -> emptyList()
                }
                
                // Load recent files (from root)
                val filesResult = getFilesUseCase("/", forceRefresh = false)
                val recentFiles = when (filesResult) {
                    is Result.Success -> filesResult.data.take(5)
                    else -> emptyList()
                }
                
                // Load cache stats
                val cacheStats = getCacheStatsUseCase()
                
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    username = username,
                    telemetry = telemetry,
                    raidArrays = raidArrays,
                    recentFiles = recentFiles,
                    cacheFileCount = cacheStats.fileCount,
                    error = null
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = "Daten konnten nicht geladen werden: ${e.message}"
                )
            }
        }
    }
    
    private fun loadTelemetryData() {
        viewModelScope.launch {
            try {
                // Only reload telemetry and RAID status, not files
                val telemetryResult = getSystemTelemetryUseCase()
                val telemetry = when (telemetryResult) {
                    is Result.Success -> telemetryResult.data
                    is Result.Error -> null
                    else -> null
                }
                
                val raidResult = getRaidStatusUseCase()
                val raidArrays = when (raidResult) {
                    is Result.Success -> raidResult.data
                    is Result.Error -> emptyList()
                    else -> emptyList()
                }
                
                _uiState.value = _uiState.value.copy(
                    telemetry = telemetry,
                    raidArrays = raidArrays
                )
            } catch (e: Exception) {
                Log.e("DashboardViewModel", "Failed to poll telemetry", e)
            }
        }
    }
    
    fun refresh() {
        loadDashboardData()
    }
    
    /**
     * Observe home network status for VPN hint banner.
     */
    private fun observeHomeNetworkState() {
        viewModelScope.launch {
            preferencesManager.getServerUrl().collectLatest { serverUrl ->
                if (serverUrl != null) {
                    networkStateManager.observeHomeNetworkStatus(serverUrl)
                        .collect { isHome -> 
                            _isInHomeNetwork.value = isHome
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
    
    fun dismissError() {
        _uiState.value = _uiState.value.copy(error = null)
    }
}

data class DashboardUiState(
    val isLoading: Boolean = false,
    val username: String = "",
    val telemetry: SystemInfo? = null,
    val raidArrays: List<RaidArray> = emptyList(),
    val recentFiles: List<FileItem> = emptyList(),
    val cacheFileCount: Int = 0,
    val error: String? = null
)

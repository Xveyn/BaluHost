package com.baluhost.android.data.network

import android.util.Log
import com.baluhost.android.data.local.datastore.PreferencesManager
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import okhttp3.OkHttpClient
import okhttp3.Request
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Checks actual BaluHost server connectivity (not just WiFi/network).
 * 
 * Features:
 * - Periodic health checks every 30 seconds
 * - On-demand connectivity testing
 * - App lifecycle awareness (checks on app resume)
 * - Combines with NetworkMonitor for complete offline detection
 * 
 * Usage:
 * ```kotlin
 * serverConnectivityChecker.isServerReachable.collect { isReachable ->
 *     // Update UI based on actual server connectivity
 * }
 * ```
 */
@Singleton
class ServerConnectivityChecker @Inject constructor(
    private val preferencesManager: PreferencesManager,
    private val okHttpClient: OkHttpClient,
    private val networkMonitor: NetworkMonitor
) {
    companion object {
        private const val TAG = "ServerConnectivityChecker"
        private const val CHECK_INTERVAL_MS = 30_000L // 30 seconds
        private const val HEALTH_ENDPOINT = "/api/health"
        private const val PING_TIMEOUT_MS = 5_000L // 5 seconds for health check
    }
    
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var periodicCheckJob: Job? = null
    
    private val _isServerReachable = MutableStateFlow(false)
    val isServerReachable: Flow<Boolean> = _isServerReachable.asStateFlow()
    
    private val _lastCheckTime = MutableStateFlow<Long?>(null)
    val lastCheckTime: Flow<Long?> = _lastCheckTime.asStateFlow()
    
    init {
        // Start periodic checks
        startPeriodicChecks()
        
        // Stop checks when network is offline (no point in pinging)
        scope.launch {
            networkMonitor.isOnline.collect { isOnline ->
                if (!isOnline) {
                    Log.d(TAG, "Network offline, marking server as unreachable")
                    _isServerReachable.value = false
                } else {
                    Log.d(TAG, "Network online, triggering immediate server check")
                    checkServerConnectivity()
                }
            }
        }
    }
    
    /**
     * Start periodic server connectivity checks.
     * Runs every 30 seconds in background.
     */
    fun startPeriodicChecks() {
        periodicCheckJob?.cancel()
        periodicCheckJob = scope.launch {
            while (isActive) {
                if (networkMonitor.isCurrentlyOnline()) {
                    checkServerConnectivity()
                }
                delay(CHECK_INTERVAL_MS)
            }
        }
        Log.d(TAG, "Started periodic server connectivity checks (every ${CHECK_INTERVAL_MS / 1000}s)")
    }
    
    /**
     * Stop periodic checks (e.g., when app goes to background).
     */
    fun stopPeriodicChecks() {
        periodicCheckJob?.cancel()
        periodicCheckJob = null
        Log.d(TAG, "Stopped periodic server connectivity checks")
    }
    
    /**
     * Trigger immediate server connectivity check.
     * Call this on app resume or user action.
     */
    suspend fun checkServerConnectivity(): Boolean {
        // Don't even try if network is offline
        if (!networkMonitor.isCurrentlyOnline()) {
            Log.d(TAG, "Network offline, skipping server check")
            _isServerReachable.value = false
            return false
        }
        
        return withContext(Dispatchers.IO) {
            try {
                val serverUrl = preferencesManager.getServerUrl().first()
                if (serverUrl.isNullOrBlank()) {
                    Log.w(TAG, "No server URL configured")
                    _isServerReachable.value = false
                    return@withContext false
                }
                
                val healthUrl = "$serverUrl$HEALTH_ENDPOINT"
                Log.d(TAG, "Checking server connectivity: $healthUrl")
                
                val request = Request.Builder()
                    .url(healthUrl)
                    .get()
                    .build()
                
                // Use a timeout-constrained client for health checks
                val healthCheckClient = okHttpClient.newBuilder()
                    .connectTimeout(PING_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS)
                    .readTimeout(PING_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS)
                    .build()
                
                val response = healthCheckClient.newCall(request).execute()
                val isReachable = response.isSuccessful
                
                Log.d(TAG, "Server connectivity check result: $isReachable (HTTP ${response.code})")
                _isServerReachable.value = isReachable
                _lastCheckTime.value = System.currentTimeMillis()
                
                response.close()
                isReachable
            } catch (e: Exception) {
                Log.e(TAG, "Server connectivity check failed", e)
                _isServerReachable.value = false
                _lastCheckTime.value = System.currentTimeMillis()
                false
            }
        }
    }
    
    /**
     * Get current server reachability status synchronously.
     */
    fun isCurrentlyReachable(): Boolean {
        return _isServerReachable.value
    }
    
    /**
     * Force immediate check and return result.
     * Suspends until check completes.
     */
    suspend fun forceCheckAndWait(): Boolean {
        return checkServerConnectivity()
    }
    
    /**
     * Cleanup resources.
     */
    fun cleanup() {
        stopPeriodicChecks()
        scope.cancel()
    }
}

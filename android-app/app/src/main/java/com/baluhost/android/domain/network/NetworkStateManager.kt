package com.baluhost.android.domain.network

import kotlinx.coroutines.flow.Flow

/**
 * Network state management abstraction.
 *
 * Provides network connectivity and VPN status information without Android dependencies.
 * Allows ViewModels to check network state without accessing Android Context directly.
 */
interface NetworkStateManager {

    /**
     * Check if VPN is currently active.
     *
     * @return True if VPN transport is active, false otherwise
     */
    fun isVpnActive(): Boolean

    /**
     * Observe VPN connection status changes.
     *
     * @return Flow that emits true when VPN is active, false when disconnected
     */
    fun observeVpnStatus(): Flow<Boolean>

    /**
     * Check if device is currently online (has internet connection).
     *
     * @return True if internet is available, false otherwise
     */
    fun isOnline(): Boolean

    /**
     * Observe network connectivity status changes.
     *
     * @return Flow that emits true when online, false when offline
     */
    fun observeOnlineStatus(): Flow<Boolean>

    /**
     * Check if network is WiFi (unmetered).
     *
     * @return True if WiFi connection, false otherwise
     */
    fun isWifi(): Boolean
}

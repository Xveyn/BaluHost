package com.baluhost.android.util

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.distinctUntilChanged

/**
 * Monitor network connectivity state.
 * 
 * Usage:
 * ```
 * networkMonitor.isConnected.collectAsState()
 * ```
 */
interface NetworkMonitor {
    val isConnected: Flow<Boolean>
    val isWifiConnected: Flow<Boolean>
    fun isCurrentlyConnected(): Boolean
    fun isCurrentlyWifiConnected(): Boolean
}

class NetworkMonitorImpl(
    private val context: Context
) : NetworkMonitor {
    
    private val connectivityManager =
        context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    
    override val isConnected: Flow<Boolean> = callbackFlow {
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                trySend(true)
            }
            
            override fun onLost(network: Network) {
                trySend(false)
            }
        }
        
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        
        connectivityManager.registerNetworkCallback(request, callback)
        
        // Emit current state
        trySend(isCurrentlyConnected())
        
        awaitClose {
            connectivityManager.unregisterNetworkCallback(callback)
        }
    }.distinctUntilChanged()
    
    override val isWifiConnected: Flow<Boolean> = callbackFlow {
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onCapabilitiesChanged(
                network: Network,
                capabilities: NetworkCapabilities
            ) {
                val isWifi = capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                trySend(isWifi)
            }
            
            override fun onLost(network: Network) {
                trySend(false)
            }
        }
        
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .build()
        
        connectivityManager.registerNetworkCallback(request, callback)
        
        // Emit current state
        trySend(isCurrentlyWifiConnected())
        
        awaitClose {
            connectivityManager.unregisterNetworkCallback(callback)
        }
    }.distinctUntilChanged()
    
    override fun isCurrentlyConnected(): Boolean {
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
    
    override fun isCurrentlyWifiConnected(): Boolean {
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
    }
}

package com.baluhost.android.service.vpn

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import androidx.core.app.NotificationCompat
import com.baluhost.android.R
import com.baluhost.android.presentation.MainActivity
import com.baluhost.android.util.Constants
import com.wireguard.android.backend.Backend
import com.wireguard.android.backend.BackendException
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.io.IOException

/**
 * VPN Service using WireGuard.
 * 
 * Manages VPN connection lifecycle and displays persistent notification.
 */
class BaluHostVpnService : VpnService() {
    
    private var vpnInterface: ParcelFileDescriptor? = null
    private var tunnel: Tunnel? = null
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    
    private val backend by lazy {
        try {
            Backend.create(this)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create WireGuard backend", e)
            null
        }
    }
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(Constants.VPN_NOTIFICATION_ID, createNotification(false))
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                val configString = intent.getStringExtra(EXTRA_CONFIG)
                if (configString != null) {
                    serviceScope.launch {
                        startVpn(configString)
                    }
                } else {
                    Log.e(TAG, "No VPN config provided")
                    stopSelf()
                }
            }
            ACTION_DISCONNECT -> {
                serviceScope.launch {
                    stopVpn()
                }
                stopSelf()
            }
            else -> {
                Log.w(TAG, "Unknown action: ${intent?.action}")
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }
    
    private suspend fun startVpn(configString: String) {
        try {
            Log.d(TAG, "Starting VPN connection")
            
            // Parse WireGuard config
            val config = Config.parse(configString.byteInputStream())
            
            // Build VPN interface
            val builder = Builder()
                .setSession("BaluHost VPN")
                .setMtu(config.`interface`.mtu.orElse(1280))
            
            // Add interface addresses
            config.`interface`.addresses.forEach { address ->
                builder.addAddress(address.address, address.mask)
            }
            
            // Add DNS servers
            config.`interface`.dnsServers.forEach { dns ->
                builder.addDnsServer(dns.hostAddress)
            }
            
            // Add allowed IPs (routes)
            config.peers.forEach { peer ->
                peer.allowedIps.forEach { allowedIp ->
                    builder.addRoute(allowedIp.address, allowedIp.mask)
                }
            }
            
            // Disallow apps (optional - exclude certain apps from VPN)
            // builder.addDisallowedApplication("com.example.app")
            
            // Establish VPN interface
            vpnInterface = builder.establish()
            
            if (vpnInterface == null) {
                throw IOException("Failed to establish VPN interface")
            }
            
            Log.d(TAG, "VPN interface established")
            
            // Create tunnel object
            tunnel = Tunnel(
                "BaluHost",
                config,
                Tunnel.State.UP,
                null
            )
            
            // Start WireGuard backend
            backend?.setState(tunnel!!, Tunnel.State.UP, config)
                ?: throw BackendException(Reason.UNKNOWN_ERROR, Exception("Backend not available"))
            
            Log.i(TAG, "VPN connection started successfully")
            
            // Update notification
            updateNotification(true)
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start VPN", e)
            updateNotification(false)
            stopSelf()
        }
    }
    
    private suspend fun stopVpn() {
        try {
            Log.d(TAG, "Stopping VPN connection")
            
            tunnel?.let { t ->
                backend?.setState(t, Tunnel.State.DOWN, null)
            }
            
            vpnInterface?.close()
            vpnInterface = null
            tunnel = null
            
            Log.i(TAG, "VPN connection stopped")
            
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping VPN", e)
        }
    }
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                Constants.VPN_NOTIFICATION_CHANNEL,
                "VPN Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows VPN connection status"
                setShowBadge(false)
            }
            
            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager.createNotificationChannel(channel)
        }
    }
    
    private fun createNotification(isConnected: Boolean): android.app.Notification {
        val title = if (isConnected) "VPN Connected" else "VPN Disconnected"
        val text = if (isConnected) "Connection active" else "Tap to connect"
        
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE
        )
        
        val disconnectIntent = Intent(this, BaluHostVpnService::class.java).apply {
            action = ACTION_DISCONNECT
        }
        
        val disconnectPendingIntent = PendingIntent.getService(
            this,
            1,
            disconnectIntent,
            PendingIntent.FLAG_IMMUTABLE
        )
        
        return NotificationCompat.Builder(this, Constants.VPN_NOTIFICATION_CHANNEL)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_launcher_foreground) // TODO: Add proper VPN icon
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply {
                if (isConnected) {
                    addAction(
                        R.drawable.ic_launcher_foreground,
                        "Disconnect",
                        disconnectPendingIntent
                    )
                }
            }
            .build()
    }
    
    private fun updateNotification(isConnected: Boolean) {
        val notification = createNotification(isConnected)
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.notify(Constants.VPN_NOTIFICATION_ID, notification)
    }
    
    override fun onDestroy() {
        serviceScope.launch {
            stopVpn()
        }
        serviceScope.cancel()
        super.onDestroy()
    }
    
    companion object {
        private const val TAG = "BaluHostVpnService"
        
        const val ACTION_CONNECT = "com.baluhost.android.vpn.CONNECT"
        const val ACTION_DISCONNECT = "com.baluhost.android.vpn.DISCONNECT"
        const val EXTRA_CONFIG = "config"
    }
}

// WireGuard Tunnel class (simplified version)
data class Tunnel(
    val name: String,
    val config: Config,
    val state: State,
    val statistics: Statistics?
) {
    enum class State {
        UP, DOWN
    }
}

// Placeholder for tunnel statistics
data class Statistics(
    val rxBytes: Long = 0,
    val txBytes: Long = 0,
    val lastHandshakeTime: Long = 0
)

// Backend exception wrapper
class BackendException(val reason: Reason, cause: Throwable) : Exception(cause) {
    enum class Reason {
        UNKNOWN_ERROR,
        UNABLE_TO_START,
        TUNNEL_MISSING
    }
}

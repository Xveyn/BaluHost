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
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * VPN Service using WireGuard.
 * 
 * Manages VPN connection lifecycle and displays persistent notification.
 */
class BaluHostVpnService : VpnService() {
    
    private var vpnInterface: ParcelFileDescriptor? = null
    private var tunnel: WgTunnel? = null
    private var backend: GoBackend? = null
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(Constants.VPN_NOTIFICATION_ID, createNotification(false))
        
        // Initialize WireGuard backend
        backend = GoBackend(applicationContext)
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
            
            if (backend == null) {
                throw IllegalStateException("WireGuard backend not initialized")
            }
            
            // Parse WireGuard config
            val config = try {
                Config.parse(configString.byteInputStream())
            } catch (e: Exception) {
                Log.e(TAG, "Failed to parse WireGuard config", e)
                throw IllegalArgumentException("Invalid WireGuard configuration", e)
            }
            
            Log.d(TAG, "Config parsed successfully, creating tunnel")
            
            // Create tunnel wrapper
            tunnel = WgTunnel("BaluHost", config)
            
            // Start tunnel using GoBackend - this handles all WireGuard crypto and routing
            backend?.setState(tunnel!!, Tunnel.State.UP, config)
            
            Log.i(TAG, "VPN tunnel started successfully")
            updateNotification(true)
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start VPN", e)
            updateNotification(false)
            throw e
        }
    }
    
    private suspend fun stopVpn() {
        try {
            Log.d(TAG, "Stopping VPN connection")
            
            // Stop tunnel using backend
            tunnel?.let { t ->
                backend?.setState(t, Tunnel.State.DOWN, null)
            }
            
            tunnel = null
            vpnInterface?.close()
            vpnInterface = null
            
            Log.i(TAG, "VPN connection stopped")
            updateNotification(false)
            
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
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply {
                if (isConnected) {
                    addAction(
                        android.R.drawable.ic_menu_close_clear_cancel,
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

/**
 * Wrapper class for WireGuard tunnel that implements the Tunnel interface
 */
private class WgTunnel(
    private val tunnelName: String,
    private val tunnelConfig: Config
) : Tunnel {
    private var currentState = Tunnel.State.DOWN
    
    override fun getName(): String = tunnelName
    
    override fun onStateChange(newState: Tunnel.State) {
        currentState = newState
        Log.d("WgTunnel", "State changed to: $newState")
    }
}

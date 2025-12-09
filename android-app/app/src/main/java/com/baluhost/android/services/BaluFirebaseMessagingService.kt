package com.baluhost.android.services

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.baluhost.android.presentation.MainActivity
import com.baluhost.android.R
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Firebase Cloud Messaging service for handling push notifications.
 * 
 * Handles:
 * - Device token refresh (register with backend)
 * - Expiration warning notifications (7d, 3d, 1h)
 * - Device removed notifications
 */
@AndroidEntryPoint
class BaluFirebaseMessagingService : FirebaseMessagingService() {
    
    companion object {
        private const val TAG = "BaluFCM"
        
        // Notification channels
        private const val CHANNEL_ID_EXPIRATION = "device_expiration"
        private const val CHANNEL_NAME_EXPIRATION = "Geräte-Autorisierung"
        private const val CHANNEL_ID_STATUS = "device_status"
        private const val CHANNEL_NAME_STATUS = "Gerätestatus"
        
        // Notification IDs
        private const val NOTIFICATION_ID_EXPIRATION = 1001
        private const val NOTIFICATION_ID_STATUS = 1002
    }
    
    @Inject
    lateinit var preferencesManager: com.baluhost.android.data.local.datastore.PreferencesManager
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }
    
    /**
     * Called when FCM registration token is created or refreshed.
     * Send token to backend for push notifications.
     */
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "New FCM token: $token")
        
        // Store token locally
        CoroutineScope(Dispatchers.IO).launch {
            preferencesManager.saveFcmToken(token)
            
            // TODO: Send token to backend
            // This requires device_id which is only available after registration
            // Token will be sent during registration or on app startup
        }
    }
    
    /**
     * Called when a message is received.
     * Parse notification and display based on type.
     */
    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        
        Log.d(TAG, "Message received from: ${message.from}")
        Log.d(TAG, "Message data: ${message.data}")
        Log.d(TAG, "Message notification: ${message.notification}")
        
        // Handle data payload
        val data = message.data
        val notificationType = data["type"] ?: ""
        
        when (notificationType) {
            "expiration_warning" -> handleExpirationWarning(data, message.notification)
            "device_removed" -> handleDeviceRemoved(data, message.notification)
            else -> {
                // Generic notification
                message.notification?.let { notification ->
                    showGenericNotification(
                        title = notification.title ?: "BaluHost",
                        body = notification.body ?: "",
                        data = data
                    )
                }
            }
        }
    }
    
    /**
     * Handle device expiration warning notification.
     * Shows notification with deep link to mobile devices page.
     */
    private fun handleExpirationWarning(data: Map<String, String>, notification: RemoteMessage.Notification?) {
        val title = notification?.title ?: "⏰ Geräte-Autorisierung läuft ab"
        val body = notification?.body ?: "Dein Gerät läuft bald ab. Tippe hier, um zu verlängern."
        val warningType = data["warning_type"] ?: "unknown"
        val deviceName = data["device_name"] ?: "Dein Gerät"
        val daysLeft = data["days_left"]?.toIntOrNull() ?: 0
        val deepLink = data["deep_link"] ?: ""
        
        // Create intent for notification tap (open app)
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("notification_type", "expiration_warning")
            putExtra("deep_link", deepLink)
            putExtra("warning_type", warningType)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            this,
            NOTIFICATION_ID_EXPIRATION,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        // Choose notification priority based on urgency
        val priority = when {
            daysLeft == 0 -> NotificationCompat.PRIORITY_MAX  // 1 hour
            daysLeft <= 3 -> NotificationCompat.PRIORITY_HIGH  // 3 days
            else -> NotificationCompat.PRIORITY_DEFAULT  // 7 days
        }
        
        // Build notification
        val notificationBuilder = NotificationCompat.Builder(this, CHANNEL_ID_EXPIRATION)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(priority)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setColor(getColor(R.color.primary))
        
        // Add action button for renewal
        val renewIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("action", "renew_device")
            putExtra("deep_link", deepLink)
        }
        
        val renewPendingIntent = PendingIntent.getActivity(
            this,
            NOTIFICATION_ID_EXPIRATION + 1,
            renewIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        notificationBuilder.addAction(
            0,  // No icon
            getString(android.R.string.ok),
            renewPendingIntent
        )
        
        // Show notification
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(NOTIFICATION_ID_EXPIRATION, notificationBuilder.build())
        
        Log.d(TAG, "Expiration warning notification shown: $warningType for $deviceName")
    }
    
    /**
     * Handle device removed notification.
     * Shows notification and clears local data.
     */
    private fun handleDeviceRemoved(data: Map<String, String>, notification: RemoteMessage.Notification?) {
        val title = notification?.title ?: "❌ Gerät deautorisiert"
        val body = notification?.body ?: "Dein Gerät wurde aus BaluHost entfernt."
        val deviceName = data["device_name"] ?: "Dein Gerät"
        
        // Create intent (opens app on login screen)
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("notification_type", "device_removed")
            putExtra("action", "logout")
        }
        
        val pendingIntent = PendingIntent.getActivity(
            this,
            NOTIFICATION_ID_STATUS,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        // Build notification
        val notificationBuilder = NotificationCompat.Builder(this, CHANNEL_ID_STATUS)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setColor(getColor(R.color.error))
        
        // Show notification
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(NOTIFICATION_ID_STATUS, notificationBuilder.build())
        
        // Clear local data (tokens, preferences)
        CoroutineScope(Dispatchers.IO).launch {
            preferencesManager.clearAll()
        }
        
        Log.d(TAG, "Device removed notification shown: $deviceName")
    }
    
    /**
     * Show generic notification (fallback).
     */
    private fun showGenericNotification(title: String, body: String, data: Map<String, String>) {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            data.forEach { (key, value) -> putExtra(key, value) }
        }
        
        val pendingIntent = PendingIntent.getActivity(
            this,
            NOTIFICATION_ID_STATUS,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val notificationBuilder = NotificationCompat.Builder(this, CHANNEL_ID_STATUS)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
        
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(NOTIFICATION_ID_STATUS, notificationBuilder.build())
    }
    
    /**
     * Create notification channels for Android 8.0+.
     */
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            
            // Expiration warnings channel (high importance)
            val expirationChannel = NotificationChannel(
                CHANNEL_ID_EXPIRATION,
                CHANNEL_NAME_EXPIRATION,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Benachrichtigungen über ablaufende Geräte-Autorisierung"
                enableVibration(true)
                enableLights(true)
            }
            
            // Device status channel (default importance)
            val statusChannel = NotificationChannel(
                CHANNEL_ID_STATUS,
                CHANNEL_NAME_STATUS,
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Benachrichtigungen über Gerätestatus-Änderungen"
            }
            
            notificationManager.createNotificationChannel(expirationChannel)
            notificationManager.createNotificationChannel(statusChannel)
            
            Log.d(TAG, "Notification channels created")
        }
    }
}

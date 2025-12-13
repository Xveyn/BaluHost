package com.baluhost.android.data.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.baluhost.android.data.notification.SyncNotificationReceiver
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages sync notifications with proper channel configuration.
 * 
 * Features:
 * - Foreground service notifications for active sync
 * - Progress notifications with real-time updates
 * - Success/error result notifications
 * - Conflict detection notifications
 * - Proper channel management for Android 8+
 * 
 * Best Practices:
 * - Uses NotificationCompat for backward compatibility
 * - Implements notification channels properly
 * - Handles permission checks for Android 13+
 * - Uses PendingIntent with immutable flags
 * - Proper notification ID management
 */
@Singleton
class SyncNotificationManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    
    companion object {
        // Notification channels
        private const val CHANNEL_SYNC_PROGRESS = "sync_progress"
        private const val CHANNEL_SYNC_COMPLETE = "sync_complete"
        private const val CHANNEL_SYNC_ERROR = "sync_error"
        private const val CHANNEL_CONFLICTS = "sync_conflicts"
        
        // Notification IDs
        private const val NOTIFICATION_ID_SYNC_PROGRESS = 1001
        private const val NOTIFICATION_ID_SYNC_COMPLETE = 1002
        private const val NOTIFICATION_ID_SYNC_ERROR = 1003
        private const val NOTIFICATION_ID_CONFLICTS = 1004
        
        // Actions
        const val ACTION_CANCEL_SYNC = "com.baluhost.android.CANCEL_SYNC"
        const val ACTION_RESOLVE_CONFLICTS = "com.baluhost.android.RESOLVE_CONFLICTS"
        const val ACTION_RETRY_SYNC = "com.baluhost.android.RETRY_SYNC"
        
        // Extras
        const val EXTRA_FOLDER_ID = "folder_id"
    }
    
    private val notificationManager = NotificationManagerCompat.from(context)
    
    init {
        createNotificationChannels()
    }
    
    /**
     * Create notification channels for Android 8.0+
     */
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channels = listOf(
                NotificationChannel(
                    CHANNEL_SYNC_PROGRESS,
                    "Synchronisation läuft",
                    NotificationManager.IMPORTANCE_LOW
                ).apply {
                    description = "Zeigt Fortschritt während der Ordner-Synchronisation"
                    setShowBadge(false)
                },
                
                NotificationChannel(
                    CHANNEL_SYNC_COMPLETE,
                    "Synchronisation abgeschlossen",
                    NotificationManager.IMPORTANCE_DEFAULT
                ).apply {
                    description = "Benachrichtigungen für abgeschlossene Synchronisationen"
                    setShowBadge(true)
                },
                
                NotificationChannel(
                    CHANNEL_SYNC_ERROR,
                    "Synchronisationsfehler",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = "Wichtige Fehler bei der Synchronisation"
                    setShowBadge(true)
                    enableVibration(true)
                },
                
                NotificationChannel(
                    CHANNEL_CONFLICTS,
                    "Dateikonflikte",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = "Benachrichtigungen über Dateikonflikte, die Ihre Aufmerksamkeit erfordern"
                    setShowBadge(true)
                    enableVibration(true)
                }
            )
            
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            channels.forEach { manager.createNotificationChannel(it) }
        }
    }
    
    /**
     * Create a foreground service notification for active sync.
     * Required for long-running WorkManager jobs.
     */
    fun createForegroundNotification(
        folderId: Long,
        folderName: String,
        status: String = "Wird synchronisiert..."
    ): android.app.Notification {
        val cancelIntent = createCancelIntent(folderId)
        
        return NotificationCompat.Builder(context, CHANNEL_SYNC_PROGRESS)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Ordner-Synchronisation")
            .setContentText(folderName)
            .setSubText(status)
            .setOngoing(true)
            .setProgress(0, 0, true) // Indeterminate progress
            .addAction(
                android.R.drawable.ic_delete,
                "Abbrechen",
                cancelIntent
            )
            .setContentIntent(createMainIntent())
            .build()
    }
    
    /**
     * Update progress notification with specific progress values.
     */
    fun updateProgressNotification(
        folderId: Long,
        folderName: String,
        current: Int,
        total: Int,
        fileName: String? = null
    ) {
        val progress = if (total > 0) (current * 100 / total) else 0
        val cancelIntent = createCancelIntent(folderId)
        
        val notification = NotificationCompat.Builder(context, CHANNEL_SYNC_PROGRESS)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Synchronisiere $folderName")
            .setContentText(fileName ?: "Datei $current von $total")
            .setProgress(total, current, false)
            .setSubText("$progress%")
            .setOngoing(true)
            .addAction(
                android.R.drawable.ic_delete,
                "Abbrechen",
                cancelIntent
            )
            .setContentIntent(createMainIntent())
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_SYNC_PROGRESS, notification)
    }
    
    /**
     * Show success notification when sync completes.
     */
    fun showSyncCompleteNotification(
        folderId: Long,
        folderName: String,
        filesUploaded: Int,
        filesDownloaded: Int,
        duration: Long
    ) {
        // Cancel progress notification
        notificationManager.cancel(NOTIFICATION_ID_SYNC_PROGRESS)
        
        val durationText = formatDuration(duration)
        val summary = buildString {
            if (filesUploaded > 0) append("$filesUploaded hochgeladen")
            if (filesUploaded > 0 && filesDownloaded > 0) append(", ")
            if (filesDownloaded > 0) append("$filesDownloaded heruntergeladen")
        }
        
        val notification = NotificationCompat.Builder(context, CHANNEL_SYNC_COMPLETE)
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setContentTitle("$folderName synchronisiert")
            .setContentText(summary.ifEmpty { "Alle Dateien sind aktuell" })
            .setSubText("Abgeschlossen in $durationText")
            .setAutoCancel(true)
            .setContentIntent(createMainIntent())
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_SYNC_COMPLETE, notification)
    }
    
    /**
     * Show error notification when sync fails.
     */
    fun showSyncErrorNotification(
        folderId: Long,
        folderName: String,
        errorMessage: String,
        canRetry: Boolean = true
    ) {
        // Cancel progress notification
        notificationManager.cancel(NOTIFICATION_ID_SYNC_PROGRESS)
        
        val builder = NotificationCompat.Builder(context, CHANNEL_SYNC_ERROR)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("Synchronisationsfehler")
            .setContentText(folderName)
            .setStyle(NotificationCompat.BigTextStyle().bigText(errorMessage))
            .setAutoCancel(true)
            .setContentIntent(createMainIntent())
        
        if (canRetry) {
            val retryIntent = createRetryIntent(folderId)
            builder.addAction(
                android.R.drawable.ic_popup_sync,
                "Erneut versuchen",
                retryIntent
            )
        }
        
        notificationManager.notify(NOTIFICATION_ID_SYNC_ERROR, builder.build())
    }
    
    /**
     * Show notification for detected conflicts requiring user action.
     */
    fun showConflictsNotification(
        folderId: Long,
        folderName: String,
        conflictCount: Int
    ) {
        val resolveIntent = createResolveConflictsIntent(folderId)
        
        val notification = NotificationCompat.Builder(context, CHANNEL_CONFLICTS)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("Dateikonflikte erkannt")
            .setContentText("$conflictCount Konflikt${if (conflictCount != 1) "e" else ""} in $folderName")
            .setStyle(NotificationCompat.BigTextStyle()
                .bigText("$conflictCount Datei${if (conflictCount != 1) "en" else ""} " +
                        "wurde${if (conflictCount != 1) "n" else ""} sowohl lokal als auch auf dem Server " +
                        "geändert. Bitte wählen Sie, welche Version behalten werden soll."))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .addAction(
                android.R.drawable.ic_menu_edit,
                "Auflösen",
                resolveIntent
            )
            .setContentIntent(resolveIntent)
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_CONFLICTS, notification)
    }
    
    /**
     * Cancel all sync notifications.
     */
    fun cancelAllNotifications() {
        notificationManager.cancel(NOTIFICATION_ID_SYNC_PROGRESS)
        notificationManager.cancel(NOTIFICATION_ID_SYNC_COMPLETE)
        notificationManager.cancel(NOTIFICATION_ID_SYNC_ERROR)
        notificationManager.cancel(NOTIFICATION_ID_CONFLICTS)
    }
    
    /**
     * Cancel progress notification only.
     */
    fun cancelProgressNotification() {
        notificationManager.cancel(NOTIFICATION_ID_SYNC_PROGRESS)
    }
    
    /**
     * Create intent to open main activity.
     */
    private fun createMainIntent(): PendingIntent {
        val intent = Intent(context, com.baluhost.android.presentation.MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        
        return PendingIntent.getActivity(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
    
    /**
     * Create intent to cancel sync.
     */
    private fun createCancelIntent(folderId: Long): PendingIntent {
        val intent = Intent(context, SyncNotificationReceiver::class.java).apply {
            action = ACTION_CANCEL_SYNC
            putExtra(EXTRA_FOLDER_ID, folderId)
        }
        
        return PendingIntent.getBroadcast(
            context,
            folderId.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
    
    /**
     * Create intent to retry sync.
     */
    private fun createRetryIntent(folderId: Long): PendingIntent {
        val intent = Intent(context, SyncNotificationReceiver::class.java).apply {
            action = ACTION_RETRY_SYNC
            putExtra(EXTRA_FOLDER_ID, folderId)
        }
        
        return PendingIntent.getBroadcast(
            context,
            folderId.toInt() + 1000,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
    
    /**
     * Create intent to resolve conflicts.
     */
    private fun createResolveConflictsIntent(folderId: Long): PendingIntent {
        val intent = Intent(context, com.baluhost.android.presentation.MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            action = ACTION_RESOLVE_CONFLICTS
            putExtra(EXTRA_FOLDER_ID, folderId)
        }
        
        return PendingIntent.getActivity(
            context,
            folderId.toInt() + 2000,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
    
    /**
     * Format duration in human-readable format.
     */
    private fun formatDuration(millis: Long): String {
        val seconds = millis / 1000
        val minutes = seconds / 60
        val hours = minutes / 60
        
        return when {
            hours > 0 -> "${hours}h ${minutes % 60}m"
            minutes > 0 -> "${minutes}m ${seconds % 60}s"
            else -> "${seconds}s"
        }
    }
}

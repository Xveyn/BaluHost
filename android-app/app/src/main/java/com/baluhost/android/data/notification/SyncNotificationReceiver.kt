package com.baluhost.android.data.notification

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.WorkManager
import com.baluhost.android.data.worker.FolderSyncWorker
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Broadcast receiver for notification actions.
 * Handles cancel sync, retry sync, and resolve conflicts actions.
 */
@AndroidEntryPoint
class SyncNotificationReceiver : BroadcastReceiver() {
    
    @Inject
    lateinit var workManager: WorkManager
    
    @Inject
    lateinit var notificationManager: SyncNotificationManager
    
    override fun onReceive(context: Context, intent: Intent) {
        val folderId = intent.getStringExtra(SyncNotificationManager.EXTRA_FOLDER_ID) ?: return
        
        when (intent.action) {
            SyncNotificationManager.ACTION_CANCEL_SYNC -> {
                // Cancel the WorkManager job
                workManager.cancelUniqueWork("${FolderSyncWorker.WORK_NAME}_$folderId")
                notificationManager.cancelProgressNotification()
            }
            
            SyncNotificationManager.ACTION_RETRY_SYNC -> {
                // Retry the sync
                val workRequest = FolderSyncWorker.createOneTimeRequest(folderId, isManual = true)
                workManager.enqueue(workRequest)
                notificationManager.cancelAllNotifications()
            }
            
            // ACTION_RESOLVE_CONFLICTS is handled by MainActivity intent
        }
    }
}

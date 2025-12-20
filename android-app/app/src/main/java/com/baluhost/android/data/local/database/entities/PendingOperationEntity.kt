package com.baluhost.android.data.local.database.entities

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey
import java.time.Instant

/**
 * Entity for pending operations in offline queue.
 * Stores operations that need to be retried when network is available.
 */
@Entity(tableName = "pending_operations")
data class PendingOperationEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    
    @ColumnInfo(name = "operation_type")
    val operationType: String,  // UPLOAD, DELETE, RENAME, etc.
    
    @ColumnInfo(name = "file_path")
    val filePath: String,
    
    @ColumnInfo(name = "local_file_path")
    val localFilePath: String? = null,  // For uploads
    
    @ColumnInfo(name = "destination_path")
    val destinationPath: String? = null,  // For moves/renames
    
    @ColumnInfo(name = "operation_data")
    val operationData: String? = null,  // JSON for additional data
    
    @ColumnInfo(name = "status")
    val status: String = "PENDING",  // PENDING, RETRYING, FAILED, COMPLETED
    
    @ColumnInfo(name = "retry_count")
    val retryCount: Int = 0,
    
    @ColumnInfo(name = "max_retries")
    val maxRetries: Int = 3,
    
    @ColumnInfo(name = "error_message")
    val errorMessage: String? = null,
    
    @ColumnInfo(name = "created_at")
    val createdAt: Instant = Instant.now(),
    
    @ColumnInfo(name = "last_retry_at")
    val lastRetryAt: Instant? = null,
    
    @ColumnInfo(name = "completed_at")
    val completedAt: Instant? = null
)

/**
 * Operation types for offline queue.
 */
object OperationType {
    const val UPLOAD = "UPLOAD"
    const val DELETE = "DELETE"
    const val RENAME = "RENAME"
    const val MOVE = "MOVE"
    const val CREATE_FOLDER = "CREATE_FOLDER"
}

/**
 * Operation status.
 */
object OperationStatus {
    const val PENDING = "PENDING"
    const val RETRYING = "RETRYING"
    const val FAILED = "FAILED"
    const val COMPLETED = "COMPLETED"
}

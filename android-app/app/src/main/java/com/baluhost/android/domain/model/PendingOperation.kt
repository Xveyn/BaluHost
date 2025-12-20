package com.baluhost.android.domain.model

import java.time.Instant

/**
 * Domain model for pending operations.
 * Represents an operation that needs to be executed when network is available.
 */
data class PendingOperation(
    val id: Long = 0,
    val operationType: OperationType,
    val filePath: String,
    val localFilePath: String? = null,
    val destinationPath: String? = null,
    val operationData: String? = null,
    val status: OperationStatus,
    val retryCount: Int = 0,
    val maxRetries: Int = 3,
    val errorMessage: String? = null,
    val createdAt: Instant = Instant.now(),
    val lastRetryAt: Instant? = null,
    val completedAt: Instant? = null
) {
    val canRetry: Boolean
        get() = status == OperationStatus.FAILED && retryCount < maxRetries
    
    val hasExceededMaxRetries: Boolean
        get() = retryCount >= maxRetries
}

/**
 * Type of operation to perform.
 */
enum class OperationType {
    UPLOAD,
    DELETE,
    RENAME,
    MOVE,
    CREATE_FOLDER
}

/**
 * Status of a pending operation.
 */
enum class OperationStatus {
    PENDING,
    RETRYING,
    FAILED,
    COMPLETED
}

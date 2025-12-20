package com.baluhost.android.data.local.database.mappers

import com.baluhost.android.data.local.database.entities.PendingOperationEntity
import com.baluhost.android.domain.model.OperationStatus
import com.baluhost.android.domain.model.OperationType
import com.baluhost.android.domain.model.PendingOperation
import java.time.Instant

/**
 * Maps PendingOperationEntity to PendingOperation domain model.
 */
fun PendingOperationEntity.toDomain(): PendingOperation {
    return PendingOperation(
        id = id,
        operationType = OperationType.valueOf(operationType),
        filePath = filePath,
        localFilePath = localFilePath,
        destinationPath = destinationPath,
        operationData = operationData,
        status = OperationStatus.valueOf(status),
        retryCount = retryCount,
        maxRetries = maxRetries,
        errorMessage = errorMessage,
        createdAt = createdAt,
        lastRetryAt = lastRetryAt,
        completedAt = completedAt
    )
}

/**
 * Maps PendingOperation domain model to PendingOperationEntity.
 */
fun PendingOperation.toEntity(): PendingOperationEntity {
    return PendingOperationEntity(
        id = id,
        operationType = operationType.name,
        filePath = filePath,
        localFilePath = localFilePath,
        destinationPath = destinationPath,
        operationData = operationData,
        status = status.name,
        retryCount = retryCount,
        maxRetries = maxRetries,
        errorMessage = errorMessage,
        createdAt = createdAt,
        lastRetryAt = lastRetryAt,
        completedAt = completedAt
    )
}

/**
 * Maps list of entities to domain models.
 */
fun List<PendingOperationEntity>.toDomain(): List<PendingOperation> {
    return map { it.toDomain() }
}

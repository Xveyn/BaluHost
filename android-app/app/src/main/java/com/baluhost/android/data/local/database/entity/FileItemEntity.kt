package com.baluhost.android.data.local.database.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.time.Instant

/**
 * Room entity for caching file items.
 */
@Entity(tableName = "file_items")
data class FileItemEntity(
    @PrimaryKey
    val path: String,
    val name: String,
    val size: Long,
    val isDirectory: Boolean,
    val modifiedAt: Long, // Stored as epoch millis
    val owner: String?,
    val permissions: String?,
    val mimeType: String?,
    val parentPath: String, // For filtering by directory
    val cachedAt: Long = System.currentTimeMillis() // When this was cached
)

package com.baluhost.android.data.local.database.entities

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey
import java.time.Instant

/**
 * File entity for local caching.
 */
@Entity(tableName = "files")
data class FileEntity(
    @PrimaryKey
    val path: String,
    val name: String,
    val size: Long,
    @ColumnInfo(name = "is_directory")
    val isDirectory: Boolean,
    @ColumnInfo(name = "modified_at")
    val modifiedAt: Instant,
    val owner: String,
    val permissions: String?,
    @ColumnInfo(name = "mime_type")
    val mimeType: String?,
    @ColumnInfo(name = "cached_at")
    val cachedAt: Instant = Instant.now()
)

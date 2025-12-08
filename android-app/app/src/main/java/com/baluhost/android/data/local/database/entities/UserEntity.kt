package com.baluhost.android.data.local.database.entities

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey
import java.time.Instant

/**
 * User entity for local storage.
 */
@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey
    val id: Int,
    val username: String,
    val email: String?,
    val role: String,
    @ColumnInfo(name = "created_at")
    val createdAt: Instant,
    @ColumnInfo(name = "is_active")
    val isActive: Boolean
)

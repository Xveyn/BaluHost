package com.baluhost.android.domain.model

import java.time.Instant

/**
 * Domain model for User.
 */
data class User(
    val id: Int,
    val username: String,
    val email: String?,
    val role: String,
    val createdAt: Instant,
    val isActive: Boolean
)

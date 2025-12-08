package com.baluhost.android.domain.model

/**
 * Authentication result containing tokens and user info.
 */
data class AuthResult(
    val accessToken: String,
    val refreshToken: String,
    val user: User,
    val device: MobileDevice? = null
)

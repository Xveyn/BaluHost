package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

// ==================== Auth DTOs ====================

data class LoginRequest(
    val username: String,
    val password: String
)

data class LoginResponse(
    @SerializedName("access_token")
    val accessToken: String,
    @SerializedName("refresh_token")
    val refreshToken: String,
    @SerializedName("token_type")
    val tokenType: String,
    val user: UserDto
)

data class RefreshTokenRequest(
    @SerializedName("refresh_token")
    val refreshToken: String
)

data class RefreshTokenResponse(
    @SerializedName("access_token")
    val accessToken: String,
    @SerializedName("token_type")
    val tokenType: String
)

data class UserDto(
    val id: Int,
    val username: String,
    val email: String?,
    val role: String,
    @SerializedName("created_at")
    val createdAt: String,
    @SerializedName("is_active")
    val isActive: Boolean
)

package com.baluhost.android.data.remote.api

import com.baluhost.android.data.remote.dto.LoginRequest
import com.baluhost.android.data.remote.dto.LoginResponse
import com.baluhost.android.data.remote.dto.RefreshTokenRequest
import com.baluhost.android.data.remote.dto.RefreshTokenResponse
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * Authentication API endpoints.
 */
interface AuthApi {
    
    @POST("auth/login")
    suspend fun login(
        @Body request: LoginRequest
    ): LoginResponse
    
    @POST("auth/refresh")
    suspend fun refreshToken(
        @Body request: RefreshTokenRequest
    ): RefreshTokenResponse
}

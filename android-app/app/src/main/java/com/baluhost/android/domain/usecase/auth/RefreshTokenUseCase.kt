package com.baluhost.android.domain.usecase.auth

import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.remote.api.AuthApi
import com.baluhost.android.data.remote.dto.RefreshTokenRequest
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.first
import javax.inject.Inject

/**
 * Use case for refreshing access token using refresh token.
 * 
 * Returns new access token on success.
 */
class RefreshTokenUseCase @Inject constructor(
    private val authApi: AuthApi,
    private val preferencesManager: PreferencesManager
) {
    
    suspend operator fun invoke(): Result<String> {
        return try {
            val refreshToken = preferencesManager.getRefreshToken().first()
                ?: return Result.Error(Exception("No refresh token available"))
            
            val response = authApi.refreshToken(
                RefreshTokenRequest(refreshToken)
            )
            
            // Save new access token
            preferencesManager.saveAccessToken(response.accessToken)
            
            Result.Success(response.accessToken)
        } catch (e: Exception) {
            // Clear tokens on refresh failure
            preferencesManager.clearTokens()
            Result.Error(Exception("Token refresh failed: ${e.message}", e))
        }
    }
}

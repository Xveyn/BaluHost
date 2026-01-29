package com.baluhost.android.data.repository

import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.remote.api.AuthApi
import com.baluhost.android.data.remote.dto.LoginRequest
import com.baluhost.android.data.remote.dto.RefreshTokenRequest
import com.baluhost.android.data.remote.dto.UserDto
import com.baluhost.android.domain.model.User
import com.baluhost.android.domain.repository.AuthRepository
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.first
import retrofit2.HttpException
import java.io.IOException
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Implementation of AuthRepository.
 *
 * Handles authentication operations with secure token storage.
 */
@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val authApi: AuthApi,
    private val preferencesManager: PreferencesManager
) : AuthRepository {

    /**
     * Authenticate user with username and password.
     */
    override suspend fun login(username: String, password: String): Result<User> {
        return try {
            val response = authApi.login(LoginRequest(username, password))

            // Save tokens securely
            preferencesManager.saveAccessToken(response.accessToken)
            preferencesManager.saveRefreshToken(response.refreshToken)

            // Save user info
            preferencesManager.saveUserId(response.user.id)
            preferencesManager.saveUsername(response.user.username)
            preferencesManager.saveUserRole(response.user.role)

            Result.Success(response.user.toDomain())
        } catch (e: HttpException) {
            when (e.code()) {
                401 -> Result.Error(Exception("Invalid username or password"))
                403 -> Result.Error(Exception("Account is inactive"))
                else -> Result.Error(Exception("Login failed: ${e.message()}"))
            }
        } catch (e: IOException) {
            Result.Error(Exception("Network error. Please check your connection."))
        } catch (e: Exception) {
            Result.Error(Exception("Login failed: ${e.message}", e))
        }
    }

    /**
     * Refresh access token using refresh token.
     */
    override suspend fun refreshToken(): Result<String> {
        return try {
            val refreshToken = preferencesManager.getRefreshToken().first()
                ?: return Result.Error(Exception("No refresh token available"))

            val response = authApi.refreshToken(RefreshTokenRequest(refreshToken))

            // Save new access token
            preferencesManager.saveAccessToken(response.accessToken)

            Result.Success(response.accessToken)
        } catch (e: HttpException) {
            when (e.code()) {
                401 -> {
                    // Refresh token expired or invalid - clear all tokens
                    preferencesManager.clearTokens()
                    Result.Error(Exception("Session expired. Please login again."))
                }
                else -> Result.Error(Exception("Token refresh failed: ${e.message()}"))
            }
        } catch (e: IOException) {
            Result.Error(Exception("Network error during token refresh"))
        } catch (e: Exception) {
            // Clear tokens on any refresh failure
            preferencesManager.clearTokens()
            Result.Error(Exception("Token refresh failed: ${e.message}", e))
        }
    }

    /**
     * Logout user and clear all authentication data.
     */
    override suspend fun logout(): Result<Unit> {
        return try {
            // Clear all tokens and user data
            preferencesManager.clearTokens()
            preferencesManager.clearAll()

            Result.Success(Unit)
        } catch (e: Exception) {
            Result.Error(Exception("Logout failed: ${e.message}", e))
        }
    }

    /**
     * Check if user is authenticated (has valid tokens).
     */
    override suspend fun isAuthenticated(): Boolean {
        val accessToken = preferencesManager.getAccessToken().first()
        return !accessToken.isNullOrBlank()
    }

    /**
     * Get current access token.
     */
    override suspend fun getAccessToken(): String? {
        return preferencesManager.getAccessToken().first()
    }

    /**
     * Get current refresh token.
     */
    override suspend fun getRefreshToken(): String? {
        return preferencesManager.getRefreshToken().first()
    }
}

/**
 * Convert UserDto to domain model User.
 */
private fun UserDto.toDomain() = User(
    id = id,
    username = username,
    email = email,
    role = role,
    createdAt = Instant.parse(createdAt),
    isActive = isActive
)

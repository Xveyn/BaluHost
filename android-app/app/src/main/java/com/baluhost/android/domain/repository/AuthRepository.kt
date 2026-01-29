package com.baluhost.android.domain.repository

import com.baluhost.android.domain.model.User
import com.baluhost.android.util.Result

/**
 * Repository interface for authentication operations.
 *
 * Handles user authentication, token management, and session lifecycle.
 */
interface AuthRepository {

    /**
     * Authenticate user with username and password.
     *
     * @param username User's username
     * @param password User's password
     * @return Result with User object or error
     */
    suspend fun login(username: String, password: String): Result<User>

    /**
     * Refresh access token using refresh token.
     *
     * @return Result with new access token or error
     */
    suspend fun refreshToken(): Result<String>

    /**
     * Logout user and clear all authentication data.
     *
     * @return Result with success status or error
     */
    suspend fun logout(): Result<Unit>

    /**
     * Check if user is authenticated (has valid tokens).
     *
     * @return True if user has access token, false otherwise
     */
    suspend fun isAuthenticated(): Boolean

    /**
     * Get current access token.
     *
     * @return Access token or null if not authenticated
     */
    suspend fun getAccessToken(): String?

    /**
     * Get current refresh token.
     *
     * @return Refresh token or null if not authenticated
     */
    suspend fun getRefreshToken(): String?
}

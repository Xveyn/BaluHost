package com.baluhost.android.data.remote.interceptors

import android.util.Log
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.remote.api.AuthApi
import com.baluhost.android.data.remote.dto.RefreshTokenRequest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

/**
 * Interceptor that adds JWT token to requests and handles token refresh on 401 errors.
 * 
 * Flow:
 * 1. Add access token to Authorization header
 * 2. If 401 response, attempt to refresh token
 * 3. Retry original request with new token
 * 4. If refresh fails, clear tokens (user needs to re-authenticate)
 */
class AuthInterceptor @Inject constructor(
    private val preferencesManager: PreferencesManager,
    private val authApi: dagger.Lazy<AuthApi>
) : Interceptor {
    
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        
        // Skip auth for login/register/refresh endpoints
        if (shouldSkipAuth(request.url.encodedPath)) {
            return chain.proceed(request)
        }
        
        // Add access token to request
        val token = runBlocking { preferencesManager.getAccessToken().first() }
        val authenticatedRequest = if (token != null) {
            request.newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        } else {
            request
        }
        
        var response = chain.proceed(authenticatedRequest)
        
        // Handle 401 - Token expired
        if (response.code == 401 && token != null) {
            response.close()
            
            synchronized(this) {
                // Check if token was refreshed by another thread
                val currentToken = runBlocking { preferencesManager.getAccessToken().first() }
                if (currentToken != token) {
                    // Token was refreshed, retry with new token
                    return chain.proceed(
                        request.newBuilder()
                            .header("Authorization", "Bearer $currentToken")
                            .build()
                    )
                }
                
                // Attempt to refresh token
                val refreshToken = runBlocking { preferencesManager.getRefreshToken().first() }
                if (refreshToken != null) {
                    try {
                        val refreshResponse = runBlocking {
                            authApi.get().refreshToken(RefreshTokenRequest(refreshToken))
                        }
                        
                        // Save new access token
                        runBlocking {
                            preferencesManager.saveAccessToken(refreshResponse.accessToken)
                        }
                        
                        Log.d(TAG, "Token refreshed successfully")
                        
                        // Retry original request with new token
                        response = chain.proceed(
                            request.newBuilder()
                                .header("Authorization", "Bearer ${refreshResponse.accessToken}")
                                .build()
                        )
                    } catch (e: Exception) {
                        Log.e(TAG, "Token refresh failed", e)
                        // Clear tokens - user needs to re-authenticate
                        runBlocking {
                            preferencesManager.clearTokens()
                        }
                    }
                } else {
                    Log.w(TAG, "No refresh token available")
                    runBlocking {
                        preferencesManager.clearTokens()
                    }
                }
            }
        }
        
        return response
    }
    
    private fun shouldSkipAuth(path: String): Boolean {
        return path.contains("/auth/login") ||
                path.contains("/auth/register") ||
                path.contains("/auth/refresh") ||
                path.contains("/mobile/register")
    }
    
    companion object {
        private const val TAG = "AuthInterceptor"
    }
}

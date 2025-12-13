package com.baluhost.android.data.remote.interceptors

import android.util.Log
import com.baluhost.android.data.remote.dto.ErrorResponse
import com.google.gson.Gson
import okhttp3.Interceptor
import okhttp3.Response
import java.io.IOException
import javax.inject.Inject

/**
 * Interceptor that logs and handles HTTP errors.
 * 
 * Converts HTTP error responses to readable error messages.
 */
class ErrorInterceptor @Inject constructor() : Interceptor {
    
    private val gson = Gson()
    
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        
        try {
            val response = chain.proceed(request)
            
            // Log errors (4xx and 5xx status codes)
            if (!response.isSuccessful) {
                // Try to peek the body, but handle if it's already consumed
                val errorMessage = try {
                    val errorBody = response.peekBody(Long.MAX_VALUE).string()
                    
                    // Try to parse error response
                    try {
                        val errorResponse = gson.fromJson(errorBody, ErrorResponse::class.java)
                        errorResponse.getErrorMessage()
                    } catch (e: Exception) {
                        errorBody.takeIf { it.isNotBlank() } ?: "HTTP ${response.code}"
                    }
                } catch (e: IllegalStateException) {
                    // Body already consumed (e.g., by AuthInterceptor during token refresh)
                    "HTTP ${response.code} ${response.message}"
                } catch (e: IOException) {
                    "HTTP ${response.code} ${response.message}"
                }
                
                Log.e(
                    TAG,
                    "HTTP Error: ${response.code} ${response.message} - $errorMessage\n" +
                            "URL: ${request.url}\n" +
                            "Method: ${request.method}"
                )
            }
            
            return response
        } catch (e: IOException) {
            Log.e(TAG, "Network error: ${e.message}", e)
            throw e
        }
    }
    
    companion object {
        private const val TAG = "ErrorInterceptor"
    }
}

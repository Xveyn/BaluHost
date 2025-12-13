package com.baluhost.android.data.remote.interceptors

import com.baluhost.android.data.local.datastore.PreferencesManager
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

/**
 * Interceptor that dynamically changes the base URL based on the server URL stored in preferences.
 * This allows the app to connect to different servers without rebuilding.
 */
class DynamicBaseUrlInterceptor @Inject constructor(
    private val preferencesManager: PreferencesManager,
    private val defaultBaseUrl: String
) : Interceptor {
    
    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()
        val originalUrl = originalRequest.url
        
        // Get server URL from preferences (blocking since we're in interceptor)
        val serverUrl = runBlocking {
            preferencesManager.getServerUrl().first()
        }
        
        // If no server URL is stored, use the original request
        if (serverUrl.isNullOrBlank()) {
            android.util.Log.d("DynamicBaseUrl", "No server URL in prefs, using default")
            return chain.proceed(originalRequest)
        }
        
        // Parse the server URL and build new base URL with /api/
        val newBaseUrl = buildBaseUrl(serverUrl)
        if (newBaseUrl == null) {
            android.util.Log.w("DynamicBaseUrl", "Invalid server URL: $serverUrl, using original")
            return chain.proceed(originalRequest)
        }
        
        // Build new URL by replacing scheme, host, port, and base path
        val newUrl = originalUrl.newBuilder()
            .scheme(newBaseUrl.scheme)
            .host(newBaseUrl.host)
            .port(newBaseUrl.port)
            .build()
        
        // Replace the path: remove old base path and add new one
        val oldPath = originalUrl.encodedPath  // e.g., "/api/files/list"
        val newPath = if (oldPath.startsWith("/api/")) {
            // Keep the endpoint path after /api/
            oldPath
        } else {
            // Add /api/ prefix if missing
            "/api$oldPath"
        }
        
        val finalUrl = newUrl.newBuilder()
            .encodedPath(newPath)
            .build()
        
        val newRequest = originalRequest.newBuilder()
            .url(finalUrl)
            .build()
        
        android.util.Log.d("DynamicBaseUrl", "Server URL from prefs: $serverUrl")
        android.util.Log.d("DynamicBaseUrl", "Original URL: ${originalRequest.url}")
        android.util.Log.d("DynamicBaseUrl", "Modified URL: ${newRequest.url}")
        
        return chain.proceed(newRequest)
    }
    
    /**
     * Builds a proper HttpUrl from the server URL stored in preferences.
     * Accepts formats like:
     * - http://192.168.178.21:8000
     * - http://192.168.178.21:8000/
     * - http://192.168.178.21:8000/api
     * - http://192.168.178.21:8000/api/
     */
    private fun buildBaseUrl(serverUrl: String): HttpUrl? {
        // Remove trailing slashes and /api suffix to normalize
        val normalized = serverUrl.trimEnd('/')
            .removeSuffix("/api")
        
        return normalized.toHttpUrlOrNull()
    }
}

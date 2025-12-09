package com.baluhost.android.domain.usecase.auth

import android.os.Build
import com.baluhost.android.BuildConfig
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.remote.api.MobileApi
import com.baluhost.android.data.remote.dto.DeviceInfoDto
import com.baluhost.android.data.remote.dto.RegisterDeviceRequest
import com.baluhost.android.domain.model.AuthResult
import com.baluhost.android.domain.model.MobileDevice
import com.baluhost.android.domain.model.User
import com.baluhost.android.util.Result
import java.time.Instant
import javax.inject.Inject

/**
 * Use case for registering a mobile device using QR code token.
 * 
 * Flow:
 * 1. Parse QR code data (token, server URL, VPN config)
 * 2. Send device registration request with device info
 * 3. Receive access/refresh tokens and user info
 * 4. Save tokens and server URL to preferences
 * 5. Return AuthResult with user and device info
 */
class RegisterDeviceUseCase @Inject constructor(
    private val mobileApi: MobileApi,
    private val preferencesManager: PreferencesManager
) {
    
    suspend operator fun invoke(
        token: String,
        serverUrl: String,
        deviceName: String = "${Build.MANUFACTURER} ${Build.MODEL}"
    ): Result<AuthResult> {
        return try {
            // CRITICAL: Create a new Retrofit instance with the server URL from QR code
            // The injected mobileApi uses BuildConfig.BASE_URL which is wrong for dynamic servers
            val finalUrl = serverUrl.let { if (it.endsWith("/")) it else "$it/" } + "api/"
            android.util.Log.d("RegisterDevice", "Using server URL: $serverUrl")
            android.util.Log.d("RegisterDevice", "Final base URL: $finalUrl")
            
            val okHttpClient = okhttp3.OkHttpClient.Builder()
                .connectTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
                .addInterceptor { chain ->
                    val request = chain.request()
                    android.util.Log.d("RegisterDevice", "Request URL: ${request.url}")
                    chain.proceed(request)
                }
                .build()
            
            val retrofit = retrofit2.Retrofit.Builder()
                .baseUrl(finalUrl)
                .client(okHttpClient)
                .addConverterFactory(retrofit2.converter.gson.GsonConverterFactory.create())
                .build()
            
            val dynamicMobileApi = retrofit.create(com.baluhost.android.data.remote.api.MobileApi::class.java)
            
            val deviceInfo = DeviceInfoDto(
                deviceName = deviceName,
                deviceType = "android",
                deviceModel = Build.MODEL,
                osVersion = "Android ${Build.VERSION.RELEASE}",
                appVersion = BuildConfig.VERSION_NAME
            )
            
            val request = RegisterDeviceRequest(
                token = token,
                deviceInfo = deviceInfo
            )
            
            val response = dynamicMobileApi.registerDevice(request)
            
            // Save authentication data
            preferencesManager.saveAccessToken(response.accessToken)
            preferencesManager.saveRefreshToken(response.refreshToken)
            preferencesManager.saveServerUrl(serverUrl)
            preferencesManager.saveUserId(response.user.id)
            preferencesManager.saveUsername(response.user.username)
            
            Result.Success(
                AuthResult(
                    accessToken = response.accessToken,
                    refreshToken = response.refreshToken,
                    user = User(
                        id = response.user.id,
                        username = response.user.username,
                        email = response.user.email,
                        role = response.user.role,
                        createdAt = Instant.parse(response.user.createdAt),
                        isActive = response.user.isActive
                    ),
                    device = MobileDevice(
                        id = response.device.id,
                        userId = response.device.userId,
                        deviceName = response.device.deviceName,
                        deviceType = response.device.deviceType,
                        deviceModel = response.device.deviceModel,
                        lastSeen = response.device.lastSeen,
                        isActive = response.device.isActive
                    )
                )
            )
        } catch (e: Exception) {
            Result.Error(Exception("Device registration failed: ${e.message}", e))
        }
    }
}

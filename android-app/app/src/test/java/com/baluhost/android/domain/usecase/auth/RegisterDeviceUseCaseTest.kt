package com.baluhost.android.domain.usecase.auth

import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.remote.api.MobileApi
import com.baluhost.android.data.remote.dto.DeviceInfoDto
import com.baluhost.android.data.remote.dto.MobileDeviceDto
import com.baluhost.android.data.remote.dto.RegisterDeviceRequest
import com.baluhost.android.data.remote.dto.RegisterDeviceResponse
import com.baluhost.android.data.remote.dto.UserDto
import com.baluhost.android.util.Result
import io.mockk.*
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*

class RegisterDeviceUseCaseTest {
    
    private lateinit var mobileApi: MobileApi
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var registerDeviceUseCase: RegisterDeviceUseCase
    
    @Before
    fun setup() {
        mobileApi = mockk()
        preferencesManager = mockk(relaxed = true)
        registerDeviceUseCase = RegisterDeviceUseCase(mobileApi, preferencesManager)
    }
    
    @After
    fun teardown() {
        clearAllMocks()
    }
    
    @Test
    fun `invoke should return success when registration is successful`() = runTest {
        // Given
        val token = "test_token"
        val serverUrl = "https://test.com"
        
        val deviceInfo = DeviceInfoDto(
            deviceType = "android",
            deviceName = "Test Device",
            osVersion = "14",
            appVersion = "1.0.0"
        )
        
        val userDto = UserDto(
            id = 1,
            username = "testuser",
            email = "test@example.com",
            isAdmin = false
        )
        
        val mobileDeviceDto = MobileDeviceDto(
            id = 1,
            userId = 1,
            deviceType = "android",
            deviceName = "Test Device",
            lastSeen = System.currentTimeMillis() / 1000,
            isActive = true
        )
        
        val response = RegisterDeviceResponse(
            accessToken = "access_token_123",
            refreshToken = "refresh_token_123",
            expiresIn = 3600,
            user = userDto,
            device = mobileDeviceDto
        )
        
        coEvery { 
            mobileApi.registerDevice(any(), any())
        } returns response
        
        // When
        val result = registerDeviceUseCase(token, serverUrl)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        assertEquals("testuser", successResult.data.user.username)
        assertEquals("Test Device", successResult.data.device.deviceName)
        
        // Verify preferences were saved
        coVerify {
            preferencesManager.saveAccessToken("access_token_123")
            preferencesManager.saveRefreshToken("refresh_token_123")
            preferencesManager.saveServerUrl(serverUrl)
            preferencesManager.saveUserId(1)
            preferencesManager.saveUsername("testuser")
        }
    }
    
    @Test
    fun `invoke should return error when API call fails`() = runTest {
        // Given
        val token = "test_token"
        val serverUrl = "https://test.com"
        val errorMessage = "Network error"
        
        coEvery { 
            mobileApi.registerDevice(any(), any())
        } throws Exception(errorMessage)
        
        // When
        val result = registerDeviceUseCase(token, serverUrl)
        
        // Then
        assertTrue(result is Result.Error)
        val errorResult = result as Result.Error
        assertTrue(errorResult.exception.message?.contains(errorMessage) == true)
        
        // Verify preferences were not saved
        coVerify(exactly = 0) {
            preferencesManager.saveAccessToken(any())
            preferencesManager.saveRefreshToken(any())
        }
    }
    
    @Test
    fun `invoke should handle null user data gracefully`() = runTest {
        // Given
        val token = "test_token"
        val serverUrl = "https://test.com"
        
        coEvery { 
            mobileApi.registerDevice(any(), any())
        } throws NullPointerException("User data is null")
        
        // When
        val result = registerDeviceUseCase(token, serverUrl)
        
        // Then
        assertTrue(result is Result.Error)
    }
}

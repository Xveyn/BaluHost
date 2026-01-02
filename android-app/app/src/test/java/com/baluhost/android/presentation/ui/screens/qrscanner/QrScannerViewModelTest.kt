package com.baluhost.android.presentation.ui.screens.qrscanner

import app.cash.turbine.test
import com.baluhost.android.domain.model.AuthResult
import com.baluhost.android.domain.model.MobileDevice
import com.baluhost.android.domain.model.User
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.domain.usecase.auth.RegisterDeviceUseCase
import com.baluhost.android.domain.usecase.vpn.ImportVpnConfigUseCase
import com.baluhost.android.util.Result
import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*

@OptIn(ExperimentalCoroutinesApi::class)
class QrScannerViewModelTest {
    
    private lateinit var registerDeviceUseCase: RegisterDeviceUseCase
    private lateinit var importVpnConfigUseCase: ImportVpnConfigUseCase
    private lateinit var viewModel: QrScannerViewModel
    
    private val testDispatcher = StandardTestDispatcher()
    
    @Before
    fun setup() {
        Dispatchers.setMain(testDispatcher)
        registerDeviceUseCase = mockk()
        importVpnConfigUseCase = mockk()
        viewModel = QrScannerViewModel(registerDeviceUseCase, importVpnConfigUseCase)
    }
    
    @After
    fun teardown() {
        Dispatchers.resetMain()
        clearAllMocks()
    }
    
    @Test
    fun `initial state should be Scanning`() = runTest {
        // Then
        viewModel.uiState.test {
            val state = awaitItem()
            assertTrue(state is QrScannerState.Scanning)
        }
    }
    
    @Test
    fun `onQrCodeScanned should transition to Processing then Success`() = runTest {
        // Given
        val qrJson = """
            {
                "token": "test_token_123",
                "server": "https://nas.example.com",
                "expires_at": 1234567890,
                "vpn_config": "base64_vpn_config_here"
            }
        """.trimIndent()
        
        val user = User(
            id = 1,
            username = "testuser",
            email = "test@example.com",
            role = "user",
            createdAt = java.time.Instant.now(),
            isActive = true
        )

        val device = MobileDevice(
            id = "device-1",
            userId = 1,
            deviceName = "Test Device",
            deviceType = "android",
            deviceModel = "ModelX",
            lastSeen = java.time.Instant.now().toString(),
            isActive = true
        )
        
        val authResult = AuthResult(accessToken = "access123", refreshToken = "refresh123", user = user, device = device)
        
        val vpnConfig = VpnConfig(
            clientId = 1,
            deviceName = "Test Device",
            publicKey = "pubkey",
            assignedIp = "10.0.0.2/24",
            configString = "config",
            serverPublicKey = "serverkey=",
            serverEndpoint = "vpn.example.com",
            serverPort = 51820,
            allowedIps = listOf("0.0.0.0/0")
        )
        
        coEvery { 
            registerDeviceUseCase(any(), any())
        } returns Result.Success(authResult)
        
        coEvery { 
            importVpnConfigUseCase(any())
        } returns Result.Success(vpnConfig)
        
        // When
        viewModel.uiState.test {
            skipItems(1) // Skip initial Scanning state
            
            viewModel.onQrCodeScanned(qrJson)
            testDispatcher.scheduler.advanceUntilIdle()
            
            // Then
            val processingState = awaitItem()
            assertTrue(processingState is QrScannerState.Processing)
            
            val successState = awaitItem()
            assertTrue(successState is QrScannerState.Success)
        }
    }
    
    @Test
    fun `onQrCodeScanned should handle invalid JSON`() = runTest {
        // Given
        val invalidJson = "not a json"
        
        // When
        viewModel.uiState.test {
            skipItems(1) // Skip initial state
            
            viewModel.onQrCodeScanned(invalidJson)
            testDispatcher.scheduler.advanceUntilIdle()
            
            // Then
            val processingState = awaitItem()
            assertTrue(processingState is QrScannerState.Processing)
            
            val errorState = awaitItem()
            assertTrue(errorState is QrScannerState.Error)
            val error = errorState as QrScannerState.Error
            assertTrue(error.message.contains("Invalid QR code") || error.message.contains("Invalid QR code format"))
        }
    }
    
    @Test
    fun `onQrCodeScanned should handle registration failure`() = runTest {
        // Given
        val qrJson = """
            {
                "token": "test_token_123",
                "server": "https://nas.example.com",
                "expires_at": 1234567890
            }
        """.trimIndent()
        
        val errorMessage = "Registration failed"
        
        coEvery { 
            registerDeviceUseCase(any(), any())
        } returns Result.Error(Exception(errorMessage))
        
        // When
        viewModel.uiState.test {
            skipItems(1)
            
            viewModel.onQrCodeScanned(qrJson)
            testDispatcher.scheduler.advanceUntilIdle()
            
            // Then
            skipItems(1) // Processing state
            
            val errorState = awaitItem()
            assertTrue(errorState is QrScannerState.Error)
            val error = errorState as QrScannerState.Error
            assertTrue(error.message.contains(errorMessage))
        }
    }
    
    @Test
    fun `onQrCodeScanned should succeed without VPN config`() = runTest {
        // Given
        val qrJson = """
            {
                "token": "test_token_123",
                "server": "https://nas.example.com",
                "expires_at": 1234567890
            }
        """.trimIndent()
        
        val user = User(
            id = 1,
            username = "testuser",
            email = "test@example.com",
            role = "user",
            createdAt = java.time.Instant.now(),
            isActive = true
        )

        val device = MobileDevice(
            id = "device-2",
            userId = 1,
            deviceName = "Test Device",
            deviceType = "android",
            deviceModel = "ModelX",
            lastSeen = java.time.Instant.now().toString(),
            isActive = true
        )

        val authResult = AuthResult(accessToken = "access2", refreshToken = "refresh2", user = user, device = device)
        
        coEvery { 
            registerDeviceUseCase(any(), any())
        } returns Result.Success(authResult)
        
        // When
        viewModel.uiState.test {
            skipItems(1)
            
            viewModel.onQrCodeScanned(qrJson)
            testDispatcher.scheduler.advanceUntilIdle()
            
            // Then
            skipItems(1) // Processing state
            
            val successState = awaitItem()
            assertTrue(successState is QrScannerState.Success)
        }
        
        coVerify(exactly = 0) {
            importVpnConfigUseCase(any())
        }
    }
    
    @Test
    fun `resetScanner should return to Scanning state`() = runTest {
        // Given - Set to error state first
        val invalidJson = "invalid"
        
        viewModel.uiState.test {
            skipItems(1)
            
            viewModel.onQrCodeScanned(invalidJson)
            testDispatcher.scheduler.advanceUntilIdle()
            
            skipItems(2) // Processing + Error states
            
            // When
            viewModel.resetScanner()
            
            // Then
            val scanningState = awaitItem()
            assertTrue(scanningState is QrScannerState.Scanning)
        }
    }
    
    @Test
    fun `should not process QR code when already processing`() = runTest {
        // Given
        val qrJson = """
            {
                "token": "test_token_123",
                "server": "https://nas.example.com",
                "expires_at": 1234567890
            }
        """.trimIndent()
        
        val user = User(1, "test", "test@test.com", role = "user", createdAt = java.time.Instant.now(), isActive = true)
        val device = MobileDevice("device-1", 1, "Test", "android", "ModelX", java.time.Instant.now().toString(), true)
        val authResult = AuthResult(accessToken = "accessSlow", refreshToken = "refreshSlow", user = user, device = device)
        
        coEvery { 
            registerDeviceUseCase(any(), any())
        } coAnswers {
            kotlinx.coroutines.delay(1000) // Simulate slow network
            Result.Success(authResult)
        }
        
        // When - Try to scan twice quickly
        viewModel.onQrCodeScanned(qrJson)
        viewModel.onQrCodeScanned(qrJson) // Second scan should be ignored
        
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Then - Should only register once
        coVerify(exactly = 1) {
            registerDeviceUseCase(any(), any())
        }
    }
}

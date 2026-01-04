package com.baluhost.android.presentation.ui.screens.vpn

import app.cash.turbine.test
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.usecase.vpn.ConnectVpnUseCase
import com.baluhost.android.domain.usecase.vpn.DisconnectVpnUseCase
import com.baluhost.android.domain.usecase.vpn.FetchVpnConfigUseCase
import com.baluhost.android.util.Result
import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*

@OptIn(ExperimentalCoroutinesApi::class)
class VpnViewModelTest {
    
    private lateinit var fetchVpnConfigUseCase: FetchVpnConfigUseCase
    private lateinit var connectVpnUseCase: ConnectVpnUseCase
    private lateinit var disconnectVpnUseCase: DisconnectVpnUseCase
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var viewModel: VpnViewModel
    private lateinit var context: android.content.Context
    
    private val testDispatcher = StandardTestDispatcher()
    
    @Before
    fun setup() {
        Dispatchers.setMain(testDispatcher)
        fetchVpnConfigUseCase = mockk()
        connectVpnUseCase = mockk()
        disconnectVpnUseCase = mockk()
        preferencesManager = mockk()
        context = mockk(relaxed = true)
        
        // Default: no VPN config
        every { preferencesManager.getVpnConfig() } returns flowOf(null)
        coEvery { fetchVpnConfigUseCase() } returns Result.Error(Exception("No config"))
        
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
    }
    
    @After
    fun teardown() {
        Dispatchers.resetMain()
        clearAllMocks()
    }
    
    @Test
    fun `initial state should check for VPN config`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf("vpn_config_string")
        
        // When
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Then
        viewModel.uiState.test {
            val state = awaitItem()
            assertTrue(state.hasConfig)
            assertFalse(state.isConnected)
        }
    }
    
    @Test
    fun `initial state should show no config when missing`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf(null)
        
        // When
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Then
        viewModel.uiState.test {
            val state = awaitItem()
            assertFalse(state.hasConfig)
            assertEquals("Keine VPN-Konfiguration gefunden", state.error)
        }
    }
    
    @Test
    fun `connect should transition to connected state on success`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf("vpn_config")
        
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        coEvery { connectVpnUseCase() } returns Result.Success(true)
        
        // When
        viewModel.uiState.test {
            skipItems(1) // Initial state
            
            viewModel.connect()
            testDispatcher.scheduler.advanceUntilIdle()
            
            // Then
            val loadingState = awaitItem()
            assertTrue(loadingState.isLoading)
            
            val connectedState = awaitItem()
            assertTrue(connectedState.isConnected)
            assertFalse(connectedState.isLoading)
            assertNull(connectedState.error)
        }
    }
    
    @Test
    fun `connect should show error on failure`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf("vpn_config")
        
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        val errorMessage = "VPN connection failed"
        coEvery { connectVpnUseCase() } returns Result.Error(Exception(errorMessage))
        
        // When
        viewModel.uiState.test {
            skipItems(1)
            
            viewModel.connect()
            testDispatcher.scheduler.advanceUntilIdle()
            
            // Then
            skipItems(1) // Loading state
            
            val errorState = awaitItem()
            assertFalse(errorState.isConnected)
            assertFalse(errorState.isLoading)
            assertEquals(errorMessage, errorState.error)
        }
    }
    
    @Test
    fun `disconnect should transition to disconnected state on success`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf("vpn_config")
        
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Connect first
        coEvery { connectVpnUseCase() } returns Result.Success(true)
        viewModel.connect()
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Setup disconnect
        coEvery { disconnectVpnUseCase() } returns Result.Success(true)
        
        // When
        viewModel.uiState.test {
            skipItems(1)
            
            viewModel.disconnect()
            testDispatcher.scheduler.advanceUntilIdle()
            
            // Then
            val loadingState = awaitItem()
            assertTrue(loadingState.isLoading)
            
            val disconnectedState = awaitItem()
            assertFalse(disconnectedState.isConnected)
            assertFalse(disconnectedState.isLoading)
        }
    }
    
    @Test
    fun `connect should do nothing when already connected`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf("vpn_config")
        
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        coEvery { connectVpnUseCase() } returns Result.Success(true)
        
        // Connect first
        viewModel.connect()
        testDispatcher.scheduler.advanceUntilIdle()
        
        // When - Try to connect again
        viewModel.connect()
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Then - Should only call once
        coVerify(exactly = 1) {
            connectVpnUseCase()
        }
    }
    
    @Test
    fun `disconnect should do nothing when already disconnected`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf("vpn_config")
        
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        // When - Try to disconnect when not connected
        viewModel.disconnect()
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Then
        coVerify(exactly = 0) {
            disconnectVpnUseCase()
        }
    }
    
    @Test
    fun `should not connect or disconnect while loading`() = runTest {
        // Given
        every { preferencesManager.getVpnConfig() } returns flowOf("vpn_config")
        
        viewModel = VpnViewModel(fetchVpnConfigUseCase, connectVpnUseCase, disconnectVpnUseCase, preferencesManager, context)
        testDispatcher.scheduler.advanceUntilIdle()
        
        coEvery { connectVpnUseCase() } coAnswers {
            kotlinx.coroutines.delay(1000)
            Result.Success(true)
        }
        
        // When - Try multiple connects rapidly
        viewModel.connect()
        viewModel.connect()
        viewModel.connect()
        
        testDispatcher.scheduler.advanceUntilIdle()
        
        // Then - Should only call once
        coVerify(exactly = 1) {
            connectVpnUseCase()
        }
    }
}

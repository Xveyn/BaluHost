package com.baluhost.android.domain.usecase.vpn

import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.util.Result
import io.mockk.*
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*
import java.util.Base64

class ImportVpnConfigUseCaseTest {
    
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var importVpnConfigUseCase: ImportVpnConfigUseCase
    
    @Before
    fun setup() {
        preferencesManager = mockk(relaxed = true)
        importVpnConfigUseCase = ImportVpnConfigUseCase(preferencesManager)
    }
    
    @After
    fun teardown() {
        clearAllMocks()
    }
    
    @Test
    fun `invoke should parse and save VPN config successfully`() = runTest {
        // Given
        val configString = """
            [Interface]
            PrivateKey = privatekeyhere123456789=
            Address = 10.0.0.2/24
            DNS = 8.8.8.8
            
            [Peer]
            PublicKey = serverkeyhere987654321=
            Endpoint = vpn.example.com:51820
            AllowedIPs = 0.0.0.0/0
            PersistentKeepalive = 25
        """.trimIndent()
        
        val base64Config = Base64.getEncoder().encodeToString(configString.toByteArray())
        
        // When
        val result = importVpnConfigUseCase(base64Config)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        val vpnConfig = successResult.data
        
        assertEquals("10.0.0.2/24", vpnConfig.assignedIp)
        assertEquals("serverkeyhere987654321=", vpnConfig.serverPublicKey)
        assertEquals("vpn.example.com:51820", vpnConfig.serverEndpoint)
        
        coVerify(exactly = 1) {
            preferencesManager.saveVpnConfig(configString)
        }
    }
    
    @Test
    fun `invoke should handle minimal config correctly`() = runTest {
        // Given
        val configString = """
            [Interface]
            Address = 10.0.0.5/32
            
            [Peer]
            PublicKey = minimal123=
            Endpoint = 192.168.1.1:51820
        """.trimIndent()
        
        val base64Config = Base64.getEncoder().encodeToString(configString.toByteArray())
        
        // When
        val result = importVpnConfigUseCase(base64Config)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        assertEquals("10.0.0.5/32", successResult.data.assignedIp)
        assertEquals("minimal123=", successResult.data.serverPublicKey)
        assertEquals("192.168.1.1:51820", successResult.data.serverEndpoint)
    }
    
    @Test
    fun `invoke should return error for invalid base64`() = runTest {
        // Given
        val invalidBase64 = "not_valid_base64!!!"
        
        // When
        val result = importVpnConfigUseCase(invalidBase64)
        
        // Then
        assertTrue(result is Result.Error)
        
        coVerify(exactly = 0) {
            preferencesManager.saveVpnConfig(any())
        }
    }
    
    @Test
    fun `invoke should return error for malformed config`() = runTest {
        // Given
        val malformedConfig = "This is not a WireGuard config"
        val base64Config = Base64.getEncoder().encodeToString(malformedConfig.toByteArray())
        
        // When
        val result = importVpnConfigUseCase(base64Config)
        
        // Then
        assertTrue(result is Result.Error)
    }
    
    @Test
    fun `invoke should handle config with multiple peers`() = runTest {
        // Given
        val configString = """
            [Interface]
            Address = 10.0.0.2/24
            
            [Peer]
            PublicKey = peer1key=
            Endpoint = server1.com:51820
            AllowedIPs = 10.0.0.0/24
            
            [Peer]
            PublicKey = peer2key=
            Endpoint = server2.com:51820
            AllowedIPs = 192.168.0.0/16
        """.trimIndent()
        
        val base64Config = Base64.getEncoder().encodeToString(configString.toByteArray())
        
        // When
        val result = importVpnConfigUseCase(base64Config)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        // Should use first peer
        assertEquals("peer1key=", successResult.data.serverPublicKey)
        assertEquals("server1.com:51820", successResult.data.serverEndpoint)
    }
}

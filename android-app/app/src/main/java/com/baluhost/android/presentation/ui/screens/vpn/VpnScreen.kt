package com.baluhost.android.presentation.ui.screens.vpn

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel

/**
 * VPN Screen - VPN connection management.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VpnScreen(
    onNavigateBack: () -> Unit,
    viewModel: VpnViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    
    // VPN permission launcher
    val vpnPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            viewModel.connect()
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("VPN Connection") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Default.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp)
        ) {
            Spacer(modifier = Modifier.height(32.dp))
            
            // VPN Status Icon
            Icon(
                imageVector = if (uiState.isConnected) Icons.Default.Lock else Icons.Default.Close,
                contentDescription = null,
                modifier = Modifier.size(80.dp),
                tint = if (uiState.isConnected) 
                    MaterialTheme.colorScheme.primary 
                else 
                    MaterialTheme.colorScheme.onSurfaceVariant
            )
            
            // Status Text
            Text(
                text = when {
                    uiState.isConnected -> "Connected"
                    uiState.isLoading -> "Connecting..."
                    else -> "Disconnected"
                },
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = if (uiState.isConnected) 
                    MaterialTheme.colorScheme.primary 
                else 
                    MaterialTheme.colorScheme.onSurface
            )
            
            // Connection Info Card
            if (uiState.hasConfig) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = "Connection Details",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        
                        HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                        
                        if (uiState.serverEndpoint != null) {
                            InfoRow(label = "Server", value = uiState.serverEndpoint)
                        }
                        
                        InfoRow(
                            label = "Status",
                            value = if (uiState.isConnected) "Active" else "Inactive"
                        )
                        
                        if (uiState.isConnected) {
                            InfoRow(label = "Encryption", value = "WireGuard")
                        }
                    }
                }
            }
            
            Spacer(modifier = Modifier.weight(1f))
            
            // Error Message
            if (uiState.error != null) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Text(
                        text = uiState.error,
                        modifier = Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
            
            // Connect/Disconnect Button
            Button(
                onClick = {
                    if (uiState.isConnected) {
                        viewModel.disconnect()
                    } else {
                        // Check VPN permission
                        val intent = VpnService.prepare(context)
                        if (intent != null) {
                            vpnPermissionLauncher.launch(intent)
                        } else {
                            viewModel.connect()
                        }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                enabled = uiState.hasConfig && !uiState.isLoading,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (uiState.isConnected) 
                        MaterialTheme.colorScheme.error 
                    else 
                        MaterialTheme.colorScheme.primary
                )
            ) {
                if (uiState.isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                } else {
                    Text(
                        text = if (uiState.isConnected) "Disconnect" else "Connect",
                        style = MaterialTheme.typography.titleMedium
                    )
                }
            }
            
            // Help Text
            if (!uiState.hasConfig) {
                Text(
                    text = "No VPN configuration found. Please scan a QR code to register this device.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun InfoRow(
    label: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium
        )
    }
}

package com.baluhost.android.presentation.ui.screens.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.clickable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.presentation.ui.screens.vpn.VpnViewModel

/**
 * Settings screen with device management options.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onNavigateBack: () -> Unit,
    onNavigateToSplash: () -> Unit,
    onNavigateToFolderSync: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
    vpnViewModel: VpnViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val vpnUiState by vpnViewModel.uiState.collectAsState()
    var showDeleteDialog by remember { mutableStateOf(false) }
    var showPinDialog by remember { mutableStateOf(false) }
    var pinSetupError by remember { mutableStateOf<String?>(null) }
    
    // Handle successful deletion - navigate to splash for re-onboarding
    LaunchedEffect(uiState.deviceDeleted) {
        if (uiState.deviceDeleted) {
            onNavigateToSplash()
        }
    }
    
    // Show error snackbar
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(uiState.error) {
        uiState.error?.let { error ->
            snackbarHostState.showSnackbar(
                message = error,
                duration = SnackbarDuration.Short
            )
            viewModel.dismissError()
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Einstellungen") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Zurück")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // User Info Card
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
                        text = "Benutzerinformationen",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    
                    InfoRow(label = "Benutzername", value = uiState.username)
                    InfoRow(label = "Server", value = uiState.serverUrl)
                    
                    uiState.deviceId?.let { deviceId ->
                        InfoRow(
                            label = "Geräte-ID",
                            value = deviceId.take(8) + "..."
                        )
                    }
                }
            }
            
            // Security Settings Card
            SecurityCard(
                uiState = uiState,
                onToggleBiometric = viewModel::toggleBiometric,
                onSetupPin = { showPinDialog = true },
                onRemovePin = viewModel::removePin,
                onToggleAppLock = viewModel::toggleAppLock,
                onSetLockTimeout = viewModel::setLockTimeout
            )
            
            // Camera Backup Settings Card (Placeholder)
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
                        text = "Kamera-Backup",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    
                    Text(
                        text = "Backup-Einstellungen werden hier angezeigt",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            
            // Cache Management Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = "Cache-Verwaltung",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    
                    // Cache Stats
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Gecachte Dateien",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = "${uiState.cacheFileCount} Dateien",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                        
                        Column(
                            modifier = Modifier.weight(1f),
                            horizontalAlignment = Alignment.End
                        ) {
                            Text(
                                text = "Älteste Datei",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = if (uiState.cacheOldestAgeDays != null) {
                                    "${uiState.cacheOldestAgeDays} Tage"
                                } else {
                                    "Keine Daten"
                                },
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    }
                    
                    Text(
                        text = "Der Cache wird automatisch bereinigt wenn er älter als 7 Tage ist oder mehr als 1000 Dateien enthält.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    
                    Button(
                        onClick = { viewModel.clearCache() },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !uiState.isClearingCache && uiState.cacheFileCount > 0
                    ) {
                        if (uiState.isClearingCache) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                color = Color.White,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Cache wird geleert...")
                        } else {
                            Text("Cache jetzt leeren")
                        }
                    }
                }
            }
            
            // Folder Sync Settings Card
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onNavigateToFolderSync),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Ordner-Synchronisation",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Verwalte synchronisierte Verzeichnisse",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Icon(
                            imageVector = Icons.Default.ChevronRight,
                            contentDescription = "Öffnen",
                            tint = MaterialTheme.colorScheme.primary
                        )
                    }
                }
            }
            
            // VPN Settings Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = "VPN-Einstellungen",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    
                    // VPN Status Card
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.1f)
                        )
                    ) {
                        Column(
                            modifier = Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Status:",
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.SemiBold
                                )
                                Text(
                                    text = if (vpnUiState.isConnected) "Verbunden" else "Getrennt",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = if (vpnUiState.isConnected) 
                                        Color(0xFF4CAF50) else Color(0xFFFF5252),
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            
                            vpnUiState.clientIp?.let { ip ->
                                InfoRow(label = "Lokale IP", value = ip)
                            }
                            
                            vpnUiState.serverEndpoint?.let { endpoint ->
                                InfoRow(label = "Server", value = endpoint)
                            }
                            
                            vpnUiState.deviceName?.let { deviceName ->
                                InfoRow(label = "Gerätename", value = deviceName)
                            }
                        }
                    }
                    
                    // VPN Action Buttons
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = {
                                if (vpnUiState.isConnected) {
                                    vpnViewModel.disconnect()
                                } else {
                                    vpnViewModel.connect()
                                }
                            },
                            modifier = Modifier.weight(1f),
                            enabled = !vpnUiState.isLoading && vpnUiState.hasConfig,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (vpnUiState.isConnected) 
                                    MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
                            )
                        ) {
                            if (vpnUiState.isLoading) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    color = Color.White,
                                    strokeWidth = 2.dp
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(if (vpnUiState.isConnected) "Trennen..." else "Verbinde...")
                            } else {
                                Text(if (vpnUiState.isConnected) "Trennen" else "Verbinden")
                            }
                        }
                        
                        Button(
                            onClick = { vpnViewModel.refreshConfig() },
                            modifier = Modifier.weight(1f),
                            enabled = !vpnUiState.isLoading,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.secondary
                            )
                        ) {
                            Icon(
                                Icons.Default.Refresh,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Aktualisieren")
                        }
                    }
                    
                    // VPN Error Message
                    vpnUiState.error?.let { error ->
                        Text(
                            text = "Fehler: $error",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 8.dp)
                        )
                    }
                }
            }
            
            Spacer(modifier = Modifier.weight(1f))
            
            // Danger Zone Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
                )
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        text = "Gefahrenzone",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error
                    )
                    
                    Text(
                        text = "Das Entfernen dieses Geräts wird die Verbindung zum Server beenden und alle lokalen Daten löschen. Diese Aktion kann nicht rückgängig gemacht werden.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    
                    Button(
                        onClick = { showDeleteDialog = true },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        ),
                        enabled = !uiState.isDeleting
                    ) {
                        if (uiState.isDeleting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                color = Color.White,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Entferne Gerät...")
                        } else {
                            Icon(
                                Icons.Default.Delete,
                                contentDescription = null,
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Gerät entfernen")
                        }
                    }
                }
            }
        }
    }
    
    // Delete Confirmation Dialog
    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = {
                Text(
                    text = "Gerät entfernen?",
                    fontWeight = FontWeight.Bold
                )
            },
            text = {
                Text(
                    text = "Möchtest du dieses Gerät wirklich von BaluHost entfernen?\n\n" +
                            "• Die Verbindung zum Server wird beendet\n" +
                            "• Alle lokalen Daten werden gelöscht\n" +
                            "• Du musst das Gerät erneut registrieren, um es wieder zu verwenden\n\n" +
                            "Diese Aktion kann nicht rückgängig gemacht werden."
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDeleteDialog = false
                        viewModel.deleteDevice()
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Entfernen")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) {
                    Text("Abbrechen")
                }
            }
        )
    }
    
    // PIN Setup Dialog
    if (showPinDialog) {
        PinSetupDialog(
            onDismiss = {
                showPinDialog = false
                pinSetupError = null
            },
            onConfirm = { pin ->
                viewModel.setupPin(
                    pin = pin,
                    onSuccess = {
                        showPinDialog = false
                        pinSetupError = null
                    },
                    onError = { error ->
                        pinSetupError = error
                    }
                )
            }
        )
    }
    
    // Show PIN setup error if any
    LaunchedEffect(pinSetupError) {
        pinSetupError?.let { error ->
            snackbarHostState.showSnackbar(
                message = error,
                duration = SnackbarDuration.Short
            )
        }
    }
}

@Composable
private fun SecurityCard(
    uiState: SettingsUiState,
    onToggleBiometric: (Boolean) -> Unit,
    onSetupPin: () -> Unit,
    onRemovePin: () -> Unit,
    onToggleAppLock: (Boolean) -> Unit,
    onSetLockTimeout: (Int) -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Sicherheit",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            
            // Biometric Authentication
            if (uiState.biometricAvailable) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Biometrische Entsperrung",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = "Fingerabdruck oder Gesichtserkennung",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Switch(
                        checked = uiState.biometricEnabled,
                        onCheckedChange = onToggleBiometric
                    )
                }
                
                Divider()
            }
            
            // PIN Setup
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "PIN",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = if (uiState.pinConfigured) "PIN konfiguriert" else "Keine PIN festgelegt",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                TextButton(
                    onClick = if (uiState.pinConfigured) onRemovePin else onSetupPin
                ) {
                    Text(if (uiState.pinConfigured) "Entfernen" else "Einrichten")
                }
            }
            
            Divider()
            
            // App Lock
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Automatische Sperre",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = "App nach Zeitüberschreitung sperren",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Switch(
                    checked = uiState.appLockEnabled,
                    onCheckedChange = onToggleAppLock,
                    enabled = uiState.biometricEnabled || uiState.pinConfigured
                )
            }
            
            // Lock Timeout Slider
            if (uiState.appLockEnabled) {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Text(
                        text = "Sperrzeit: ${uiState.lockTimeoutMinutes} Minuten",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Slider(
                        value = uiState.lockTimeoutMinutes.toFloat(),
                        onValueChange = { onSetLockTimeout(it.toInt()) },
                        valueRange = 1f..30f,
                        steps = 28 // 1, 2, 3, ..., 30
                    )
                }
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
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
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

package com.baluhost.android.presentation.ui.screens.sync

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.presentation.ui.components.GlassCard
import com.baluhost.android.presentation.ui.theme.Slate400
import com.baluhost.android.presentation.ui.theme.Slate100
import com.baluhost.android.domain.model.sync.SyncStatus

/**
 * Screen for managing device sync folders and status.
 * Shows a list of local folders, toggle to enable sync, and a status indicator.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SyncScreen(
    viewModel: SyncViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Sync") }
            )
        }
    ) { padding ->
        Box(modifier = Modifier
            .fillMaxSize()
            .padding(padding)) {

            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                item {
                    Text(
                        text = "Wähle Verzeichnisse auf diesem Gerät zur Synchronisation:",
                        style = MaterialTheme.typography.bodyLarge,
                        color = Slate100
                    )
                }

                items(state.folders) { folder ->
                    GlassCard(intensity = com.baluhost.android.presentation.ui.components.GlassIntensity.Medium) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp)
                                .clickable { viewModel.toggleFolderEnabled(folder.path) },
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(folder.displayName, style = MaterialTheme.typography.bodyLarge, color = Slate100)
                                Text(folder.path, style = MaterialTheme.typography.bodySmall, color = Slate400)
                            }

                            Row(verticalAlignment = Alignment.CenterVertically) {
                                when (folder.syncStatus) {
                                    SyncStatus.IDLE -> Icon(Icons.Default.CloudDone, contentDescription = "Idle", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                    SyncStatus.SYNCING -> Icon(Icons.Default.Sync, contentDescription = "Syncing", tint = MaterialTheme.colorScheme.primary)
                                    SyncStatus.ERROR -> Icon(Icons.Default.CloudOff, contentDescription = "Error", tint = MaterialTheme.colorScheme.error)
                                    SyncStatus.PAUSED -> Icon(Icons.Default.CloudOff, contentDescription = "Paused", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                }

                                Spacer(modifier = Modifier.width(12.dp))

                                Switch(checked = folder.enabled, onCheckedChange = { viewModel.toggleFolderEnabled(folder.path) })
                            }
                        }
                    }
                }
            }
        }
    }
}

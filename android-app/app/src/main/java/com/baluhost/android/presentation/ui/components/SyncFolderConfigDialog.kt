package com.baluhost.android.presentation.ui.components

import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.baluhost.android.domain.model.sync.*
import com.baluhost.android.presentation.ui.theme.*
import com.baluhost.android.presentation.ui.screens.sync.SyncFolderCreateConfig
import com.baluhost.android.presentation.ui.screens.sync.SyncFolderUpdateConfig

/**
 * Configuration dialog for sync folder settings.
 * Supports both creating new folders and editing existing ones.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SyncFolderConfigDialog(
    folder: SyncFolderConfig?,
    folderUri: Uri?,
    folderName: String?,
    onConfirm: (Any) -> Unit,
    onDismiss: () -> Unit
) {
    val isEditMode = folder != null
    
    var remotePath by remember { 
        mutableStateOf(folder?.remotePath ?: "/sync/${folderName ?: "folder"}") 
    }
    var syncType by remember { 
        mutableStateOf(folder?.syncType ?: SyncType.UPLOAD_ONLY) 
    }
    var autoSync by remember { 
        mutableStateOf(folder?.autoSync ?: true) 
    }
    var conflictResolution by remember { 
        mutableStateOf(folder?.conflictResolution ?: ConflictResolution.KEEP_NEWEST) 
    }
    var excludePatterns by remember { 
        mutableStateOf(folder?.excludePatterns?.joinToString(", ") ?: ".tmp, .cache, node_modules") 
    }
    
    var showSyncTypeMenu by remember { mutableStateOf(false) }
    var showConflictMenu by remember { mutableStateOf(false) }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.fillMaxWidth(0.95f),
        icon = {
            Icon(
                imageVector = Icons.Default.Settings,
                contentDescription = null,
                tint = Sky400,
                modifier = Modifier.size(32.dp)
            )
        },
        title = {
            Text(
                text = if (isEditMode) "Ordner bearbeiten" else "Sync-Ordner konfigurieren",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Folder info
                if (!isEditMode && folderName != null) {
                    GlassCard(intensity = GlassIntensity.Light) {
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.Folder,
                                contentDescription = null,
                                tint = Sky400,
                                modifier = Modifier.size(24.dp)
                            )
                            Column {
                                Text(
                                    text = "Lokaler Ordner:",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Slate400
                                )
                                Text(
                                    text = folderName,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = Slate100,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                        }
                    }
                }
                
                // Remote path
                OutlinedTextField(
                    value = remotePath,
                    onValueChange = { remotePath = it },
                    label = { Text("Remote-Pfad") },
                    leadingIcon = {
                        Icon(Icons.Default.CloudUpload, contentDescription = null)
                    },
                    placeholder = { Text("/sync/folder") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Sky400,
                        focusedLabelColor = Sky400,
                        focusedLeadingIconColor = Sky400,
                        unfocusedBorderColor = Slate600,
                        unfocusedLabelColor = Slate400,
                        cursorColor = Sky400
                    )
                )
                
                // Sync type
                ExposedDropdownMenuBox(
                    expanded = showSyncTypeMenu,
                    onExpandedChange = { showSyncTypeMenu = it }
                ) {
                    OutlinedTextField(
                        value = getSyncTypeLabel(syncType),
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Synchronisationsart") },
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = showSyncTypeMenu)
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Sky400,
                            focusedLabelColor = Sky400,
                            unfocusedBorderColor = Slate600,
                            unfocusedLabelColor = Slate400
                        )
                    )
                    
                    ExposedDropdownMenu(
                        expanded = showSyncTypeMenu,
                        onDismissRequest = { showSyncTypeMenu = false }
                    ) {
                        SyncType.entries.forEach { type ->
                            DropdownMenuItem(
                                text = { 
                                    Column {
                                        Text(
                                            text = getSyncTypeLabel(type),
                                            style = MaterialTheme.typography.bodyMedium
                                        )
                                        Text(
                                            text = getSyncTypeDescription(type),
                                            style = MaterialTheme.typography.bodySmall,
                                            color = Slate400
                                        )
                                    }
                                },
                                onClick = {
                                    syncType = type
                                    showSyncTypeMenu = false
                                },
                                leadingIcon = {
                                    Icon(
                                        imageVector = getSyncTypeIcon(type),
                                        contentDescription = null,
                                        tint = if (syncType == type) Sky400 else Slate400
                                    )
                                }
                            )
                        }
                    }
                }
                
                // Auto-sync toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Automatische Synchronisation",
                            style = MaterialTheme.typography.bodyMedium,
                            color = Slate100,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = "Sync im Hintergrund alle 6 Stunden",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate400
                        )
                    }
                    Switch(
                        checked = autoSync,
                        onCheckedChange = { autoSync = it },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = Sky400,
                            checkedTrackColor = Sky400.copy(alpha = 0.5f)
                        )
                    )
                }
                
                Divider(color = Slate700)
                
                // Conflict resolution
                ExposedDropdownMenuBox(
                    expanded = showConflictMenu,
                    onExpandedChange = { showConflictMenu = it }
                ) {
                    OutlinedTextField(
                        value = getConflictResolutionLabel(conflictResolution),
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Konfliktlösung") },
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = showConflictMenu)
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Sky400,
                            focusedLabelColor = Sky400,
                            unfocusedBorderColor = Slate600,
                            unfocusedLabelColor = Slate400
                        )
                    )
                    
                    ExposedDropdownMenu(
                        expanded = showConflictMenu,
                        onDismissRequest = { showConflictMenu = false }
                    ) {
                        ConflictResolution.entries.forEach { resolution ->
                            DropdownMenuItem(
                                text = {
                                    Column {
                                        Text(
                                            text = getConflictResolutionLabel(resolution),
                                            style = MaterialTheme.typography.bodyMedium
                                        )
                                        Text(
                                            text = getConflictResolutionDescription(resolution),
                                            style = MaterialTheme.typography.bodySmall,
                                            color = Slate400
                                        )
                                    }
                                },
                                onClick = {
                                    conflictResolution = resolution
                                    showConflictMenu = false
                                },
                                leadingIcon = {
                                    Icon(
                                        imageVector = Icons.Default.MergeType,
                                        contentDescription = null,
                                        tint = if (conflictResolution == resolution) Sky400 else Slate400
                                    )
                                }
                            )
                        }
                    }
                }
                
                // Exclude patterns
                OutlinedTextField(
                    value = excludePatterns,
                    onValueChange = { excludePatterns = it },
                    label = { Text("Ausschlussmuster") },
                    leadingIcon = {
                        Icon(Icons.Default.Block, contentDescription = null)
                    },
                    placeholder = { Text(".tmp, .cache, node_modules") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                    maxLines = 3,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Sky400,
                        focusedLabelColor = Sky400,
                        focusedLeadingIconColor = Sky400,
                        unfocusedBorderColor = Slate600,
                        unfocusedLabelColor = Slate400,
                        cursorColor = Sky400
                    )
                )
                
                Text(
                    text = "Kommagetrennte Liste von Mustern, die ignoriert werden sollen",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate400
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val patterns = excludePatterns.split(",").map { it.trim() }.filter { it.isNotEmpty() }
                    
                    if (isEditMode) {
                        onConfirm(
                            SyncFolderUpdateConfig(
                                folderId = folder!!.id,
                                remotePath = remotePath,
                                syncType = syncType,
                                autoSync = autoSync,
                                conflictResolution = conflictResolution,
                                excludePatterns = patterns
                            )
                        )
                    } else {
                        onConfirm(
                            SyncFolderCreateConfig(
                                localUri = folderUri!!,
                                remotePath = remotePath,
                                syncType = syncType,
                                autoSync = autoSync,
                                conflictResolution = conflictResolution,
                                excludePatterns = patterns
                            )
                        )
                    }
                },
                enabled = remotePath.isNotEmpty(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Green500
                )
            ) {
                Text(if (isEditMode) "Speichern" else "Erstellen")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Abbrechen", color = Slate300)
            }
        },
        containerColor = Slate900,
        iconContentColor = Sky400,
        titleContentColor = Slate100,
        textContentColor = Slate300
    )
}

private fun getSyncTypeLabel(type: SyncType): String = when (type) {
    SyncType.UPLOAD_ONLY -> "Nur hochladen"
    SyncType.DOWNLOAD_ONLY -> "Nur herunterladen"
    SyncType.BIDIRECTIONAL -> "Bidirektional"
}

private fun getSyncTypeDescription(type: SyncType): String = when (type) {
    SyncType.UPLOAD_ONLY -> "Dateien nur zum Server hochladen"
    SyncType.DOWNLOAD_ONLY -> "Dateien nur vom Server herunterladen"
    SyncType.BIDIRECTIONAL -> "In beide Richtungen synchronisieren"
}

private fun getSyncTypeIcon(type: SyncType) = when (type) {
    SyncType.UPLOAD_ONLY -> Icons.Default.Upload
    SyncType.DOWNLOAD_ONLY -> Icons.Default.Download
    SyncType.BIDIRECTIONAL -> Icons.Default.SyncAlt
}

private fun getConflictResolutionLabel(resolution: ConflictResolution): String = when (resolution) {
    ConflictResolution.KEEP_LOCAL -> "Lokal behalten"
    ConflictResolution.KEEP_SERVER -> "Server behalten"
    ConflictResolution.KEEP_NEWEST -> "Neueste behalten"
    ConflictResolution.ASK_USER -> "Jedes Mal fragen"
}

private fun getConflictResolutionDescription(resolution: ConflictResolution): String = when (resolution) {
    ConflictResolution.KEEP_LOCAL -> "Immer lokale Version bevorzugen"
    ConflictResolution.KEEP_SERVER -> "Immer Server-Version bevorzugen"
    ConflictResolution.KEEP_NEWEST -> "Neuere Version nach Zeitstempel wählen"
    ConflictResolution.ASK_USER -> "Bei jedem Konflikt nachfragen"
}


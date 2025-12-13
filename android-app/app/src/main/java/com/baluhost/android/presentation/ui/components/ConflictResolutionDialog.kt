package com.baluhost.android.presentation.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.baluhost.android.domain.model.sync.ConflictResolution
import com.baluhost.android.domain.model.sync.FileConflict
import com.baluhost.android.presentation.ui.theme.*
import java.text.SimpleDateFormat
import java.util.*

/**
 * Dialog for resolving file sync conflicts.
 * 
 * Features:
 * - Shows conflicting files with metadata (size, timestamp)
 * - Allows per-file resolution or batch resolution
 * - Visual indicators for local vs remote versions
 * - Material 3 glassmorphism design
 * 
 * Best Practices:
 * - Immutable state management
 * - Clear visual hierarchy
 * - Accessible UI with semantic colors
 * - Responsive layout
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConflictResolutionDialog(
    conflicts: List<FileConflict>,
    onResolve: (Map<String, ConflictResolution>) -> Unit,
    onDismiss: () -> Unit,
    defaultResolution: ConflictResolution = ConflictResolution.KEEP_NEWEST
) {
    // Track resolution for each file
    val resolutions = remember {
        mutableStateMapOf<String, ConflictResolution>().apply {
            conflicts.forEach { conflict ->
                this[conflict.relativePath] = defaultResolution
            }
        }
    }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier
            .fillMaxWidth(0.95f)
            .fillMaxHeight(0.85f),
        icon = {
            Icon(
                imageVector = Icons.Default.MergeType,
                contentDescription = null,
                tint = Orange500,
                modifier = Modifier.size(32.dp)
            )
        },
        title = {
            Column {
                Text(
                    text = "Konflikte lösen",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "${conflicts.size} Datei${if (conflicts.size != 1) "en" else ""} mit Konflikten",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Slate400
                )
            }
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Batch resolution options
                GlassCard(intensity = GlassIntensity.Light) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            text = "Alle Konflikte lösen:",
                            style = MaterialTheme.typography.labelMedium,
                            color = Slate300,
                            fontWeight = FontWeight.SemiBold
                        )
                        
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            BatchResolutionButton(
                                icon = Icons.Default.Upload,
                                text = "Lokal",
                                onClick = {
                                    conflicts.forEach { conflict ->
                                        resolutions[conflict.relativePath] = ConflictResolution.KEEP_LOCAL
                                    }
                                },
                                modifier = Modifier.weight(1f)
                            )
                            
                            BatchResolutionButton(
                                icon = Icons.Default.Download,
                                text = "Server",
                                onClick = {
                                    conflicts.forEach { conflict ->
                                        resolutions[conflict.relativePath] = ConflictResolution.KEEP_SERVER
                                    }
                                },
                                modifier = Modifier.weight(1f)
                            )
                            
                            BatchResolutionButton(
                                icon = Icons.Default.Schedule,
                                text = "Neuste",
                                onClick = {
                                    conflicts.forEach { conflict ->
                                        resolutions[conflict.relativePath] = ConflictResolution.KEEP_NEWEST
                                    }
                                },
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                }
                
                Divider(color = Slate700)
                
                // Individual conflict resolution
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(conflicts) { conflict ->
                        ConflictCard(
                            conflict = conflict,
                            selectedResolution = resolutions[conflict.relativePath] 
                                ?: ConflictResolution.KEEP_NEWEST,
                            onResolutionChange = { resolution ->
                                resolutions[conflict.relativePath] = resolution
                            }
                        )
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onResolve(resolutions.toMap())
                },
                colors = ButtonDefaults.buttonColors(
                    containerColor = Green500
                )
            ) {
                Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Lösen (${conflicts.size})")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Abbrechen", color = Slate300)
            }
        },
        containerColor = Slate900,
        iconContentColor = Orange500,
        titleContentColor = Slate100,
        textContentColor = Slate300
    )
}

@Composable
private fun BatchResolutionButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.height(40.dp),
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = Sky400
        ),
        border = androidx.compose.foundation.BorderStroke(1.dp, Slate600)
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            modifier = Modifier.size(16.dp)
        )
        Spacer(modifier = Modifier.width(4.dp))
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall
        )
    }
}

@Composable
private fun ConflictCard(
    conflict: FileConflict,
    selectedResolution: ConflictResolution,
    onResolutionChange: (ConflictResolution) -> Unit
) {
    GlassCard(intensity = GlassIntensity.Medium) {
        Column(
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // File name
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Description,
                    contentDescription = null,
                    tint = Sky400,
                    modifier = Modifier.size(20.dp)
                )
                Text(
                    text = conflict.fileName,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = Slate100,
                    modifier = Modifier.weight(1f)
                )
            }
            
            // Path
            Text(
                text = conflict.relativePath,
                style = MaterialTheme.typography.bodySmall,
                color = Slate400
            )
            
            Divider(color = Slate700)
            
            // Local vs Remote comparison
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Local version
                VersionCard(
                    title = "Lokal",
                    icon = Icons.Default.PhoneAndroid,
                    size = conflict.localSize,
                    timestamp = conflict.localModifiedAt,
                    isSelected = selectedResolution == ConflictResolution.KEEP_LOCAL,
                    onClick = { onResolutionChange(ConflictResolution.KEEP_LOCAL) },
                    modifier = Modifier.weight(1f)
                )
                
                // Remote version
                VersionCard(
                    title = "Server",
                    icon = Icons.Default.Cloud,
                    size = conflict.remoteSize,
                    timestamp = conflict.remoteModifiedAt,
                    isSelected = selectedResolution == ConflictResolution.KEEP_SERVER,
                    onClick = { onResolutionChange(ConflictResolution.KEEP_SERVER) },
                    modifier = Modifier.weight(1f)
                )
            }
            
            // Resolution strategy
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = null,
                    tint = Slate400,
                    modifier = Modifier.size(16.dp)
                )
                Text(
                    text = "Strategie:",
                    style = MaterialTheme.typography.labelSmall,
                    color = Slate400
                )
                
                // Resolution chips
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    ResolutionChip(
                        text = "Neuste",
                        isSelected = selectedResolution == ConflictResolution.KEEP_NEWEST,
                        onClick = { onResolutionChange(ConflictResolution.KEEP_NEWEST) }
                    )
                }
            }
        }
    }
}

@Composable
private fun VersionCard(
    title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    size: Long,
    timestamp: Long,
    isSelected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val backgroundColor = if (isSelected) Sky900.copy(alpha = 0.3f) else Slate800.copy(alpha = 0.5f)
    val borderColor = if (isSelected) Sky400 else Slate600
    
    Surface(
        modifier = modifier,
        onClick = onClick,
        shape = MaterialTheme.shapes.medium,
        color = backgroundColor,
        border = androidx.compose.foundation.BorderStroke(
            width = if (isSelected) 2.dp else 1.dp,
            color = borderColor
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = if (isSelected) Sky400 else Slate400,
                    modifier = Modifier.size(18.dp)
                )
                Text(
                    text = title,
                    style = MaterialTheme.typography.labelMedium,
                    color = if (isSelected) Sky400 else Slate300,
                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                )
                
                if (isSelected) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = null,
                        tint = Green500,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
            
            Text(
                text = formatBytes(size),
                style = MaterialTheme.typography.bodySmall,
                color = Slate300
            )
            
            Text(
                text = formatTimestamp(timestamp),
                style = MaterialTheme.typography.bodySmall,
                color = Slate400
            )
        }
    }
}

@Composable
private fun ResolutionChip(
    text: String,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    FilterChip(
        selected = isSelected,
        onClick = onClick,
        label = {
            Text(
                text = text,
                style = MaterialTheme.typography.labelSmall
            )
        },
        leadingIcon = if (isSelected) {
            {
                Icon(
                    imageVector = Icons.Default.Check,
                    contentDescription = null,
                    modifier = Modifier.size(14.dp)
                )
            }
        } else null,
        colors = FilterChipDefaults.filterChipColors(
            selectedContainerColor = Sky400.copy(alpha = 0.2f),
            selectedLabelColor = Sky400,
            selectedLeadingIconColor = Sky400
        )
    )
}

private fun formatBytes(bytes: Long): String {
    val units = arrayOf("B", "KB", "MB", "GB")
    var size = bytes.toDouble()
    var unitIndex = 0
    
    while (size >= 1024 && unitIndex < units.size - 1) {
        size /= 1024
        unitIndex++
    }
    
    return "%.1f %s".format(size, units[unitIndex])
}

private fun formatTimestamp(timestamp: Long): String {
    val sdf = SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.GERMAN)
    return sdf.format(Date(timestamp))
}

package com.baluhost.android.presentation.ui.screens.pending

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
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.domain.model.OperationStatus
import com.baluhost.android.domain.model.OperationType
import com.baluhost.android.domain.model.PendingOperation
import com.baluhost.android.presentation.ui.theme.*
import java.time.format.DateTimeFormatter

/**
 * Screen showing all pending/failed operations in the queue.
 * Allows manual retry and cancellation.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PendingOperationsScreen(
    onNavigateBack: () -> Unit,
    viewModel: PendingOperationsViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Ausstehende Operationen") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Zurück")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Sky400,
                    titleContentColor = Slate950,
                    navigationIconContentColor = Slate950
                )
            )
        }
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            when {
                uiState.isLoading -> {
                    CircularProgressIndicator(
                        modifier = Modifier.align(Alignment.Center),
                        color = Sky400
                    )
                }
                uiState.operations.isEmpty() -> {
                    EmptyState(modifier = Modifier.align(Alignment.Center))
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        items(
                            items = uiState.operations,
                            key = { it.id }
                        ) { operation ->
                            OperationCard(
                                operation = operation,
                                onRetry = { viewModel.retryOperation(operation.id) },
                                onCancel = { viewModel.cancelOperation(operation.id) }
                            )
                        }
                    }
                }
            }
            
            // Snackbar for messages
            uiState.message?.let { message ->
                LaunchedEffect(message) {
                    // Show snackbar
                    viewModel.clearMessage()
                }
            }
        }
    }
}

@Composable
private fun EmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.CheckCircle,
            contentDescription = null,
            tint = Green500,
            modifier = Modifier.size(64.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = "Keine ausstehenden Operationen",
            style = MaterialTheme.typography.titleMedium,
            color = Slate700
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Alle Operationen wurden erfolgreich abgeschlossen",
            style = MaterialTheme.typography.bodyMedium,
            color = Slate500
        )
    }
}

@Composable
private fun OperationCard(
    operation: PendingOperation,
    onRetry: () -> Unit,
    onCancel: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = when (operation.status) {
                OperationStatus.PENDING -> Slate100
                OperationStatus.RETRYING -> Sky100
                OperationStatus.FAILED -> Red500.copy(alpha = 0.1f)
                OperationStatus.COMPLETED -> Green500.copy(alpha = 0.1f)
            }
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            // Header: Operation Type + Status
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = when (operation.operationType) {
                            OperationType.UPLOAD -> Icons.Default.Upload
                            OperationType.DELETE -> Icons.Default.Delete
                            OperationType.RENAME -> Icons.Default.Edit
                            OperationType.CREATE_FOLDER -> Icons.Default.CreateNewFolder
                            OperationType.MOVE -> Icons.Default.DriveFileMove
                        },
                        contentDescription = null,
                        tint = Slate700,
                        modifier = Modifier.size(20.dp)
                    )
                    Text(
                        text = operation.operationType.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                }
                
                StatusBadge(status = operation.status)
            }
            
            Spacer(modifier = Modifier.height(8.dp))
            
            // File Path
            Text(
                text = operation.filePath,
                style = MaterialTheme.typography.bodyMedium,
                color = Slate700
            )
            
            // Retry Count
            if (operation.retryCount > 0) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Versuche: ${operation.retryCount}/${operation.maxRetries}",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate500
                )
            }
            
            // Error Message
            operation.errorMessage?.let { error ->
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    color = Red500.copy(alpha = 0.1f),
                    shape = MaterialTheme.shapes.small
                ) {
                    Row(
                        modifier = Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Error,
                            contentDescription = null,
                            tint = Red500,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = error,
                            style = MaterialTheme.typography.bodySmall,
                            color = Red600
                        )
                    }
                }
            }
            
            // Timestamps
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text(
                    text = "Erstellt: ${formatTimestamp(operation.createdAt)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate500
                )
                operation.lastRetryAt?.let { lastRetry ->
                    Text(
                        text = "Letzter Versuch: ${formatTimestamp(lastRetry)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate500
                    )
                }
            }
            
            // Action Buttons
            if (operation.status != OperationStatus.COMPLETED) {
                Spacer(modifier = Modifier.height(12.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Cancel Button
                    TextButton(
                        onClick = onCancel,
                        colors = ButtonDefaults.textButtonColors(
                            contentColor = Red500
                        )
                    ) {
                        Icon(
                            imageVector = Icons.Default.Cancel,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Abbrechen")
                    }
                    
                    Spacer(modifier = Modifier.width(8.dp))
                    
                    // Retry Button
                    if (operation.canRetry) {
                        Button(
                            onClick = onRetry,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Sky400,
                                contentColor = Slate950
                            )
                        ) {
                            Icon(
                                imageVector = Icons.Default.Refresh,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Wiederholen")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusBadge(status: OperationStatus) {
    val (color, icon, text) = when (status) {
        OperationStatus.PENDING -> Triple(Slate600, Icons.Default.Schedule, "Ausstehend")
        OperationStatus.RETRYING -> Triple(Sky600, Icons.Default.Sync, "Wird wiederholt")
        OperationStatus.FAILED -> Triple(Red600, Icons.Default.Error, "Fehlgeschlagen")
        OperationStatus.COMPLETED -> Triple(Green600, Icons.Default.CheckCircle, "Abgeschlossen")
    }
    
    Surface(
        color = color.copy(alpha = 0.15f),
        shape = MaterialTheme.shapes.small
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(14.dp)
            )
            Text(
                text = text,
                style = MaterialTheme.typography.labelSmall,
                color = color,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

private fun formatTimestamp(instant: java.time.Instant): String {
    val formatter = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")
    return formatter.format(
        java.time.LocalDateTime.ofInstant(
            instant,
            java.time.ZoneId.systemDefault()
        )
    )
}

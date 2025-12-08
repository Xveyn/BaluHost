package com.baluhost.android.presentation.ui.screens.files

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.domain.model.FileItem
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

/**
 * Files Screen - Main file browser.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FilesScreen(
    onNavigateToVpn: () -> Unit,
    viewModel: FilesViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    var showDeleteDialog by remember { mutableStateOf<FileItem?>(null) }
    var showMenu by remember { mutableStateOf(false) }
    
    // File picker for upload
    val filePicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let {
            try {
                val inputStream = context.contentResolver.openInputStream(it)
                val tempFile = File(context.cacheDir, "upload_${System.currentTimeMillis()}")
                inputStream?.use { input ->
                    tempFile.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }
                viewModel.uploadFile(tempFile)
            } catch (e: Exception) {
                // Error handled by ViewModel
            }
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { 
                    Column {
                        Text("Files")
                        if (uiState.currentPath.isNotEmpty()) {
                            Text(
                                text = "/${uiState.currentPath}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                },
                navigationIcon = {
                    if (uiState.currentPath.isNotEmpty()) {
                        IconButton(onClick = { viewModel.navigateBack() }) {
                            Icon(
                                imageVector = Icons.Default.ArrowBack,
                                contentDescription = "Back"
                            )
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { showMenu = true }) {
                        Icon(
                            imageVector = Icons.Default.Menu,
                            contentDescription = "Menu"
                        )
                    }
                    DropdownMenu(
                        expanded = showMenu,
                        onDismissRequest = { showMenu = false }
                    ) {
                        DropdownMenuItem(
                            text = { Text("VPN Settings") },
                            onClick = {
                                showMenu = false
                                onNavigateToVpn()
                            },
                            leadingIcon = {
                                Icon(Icons.Default.Lock, contentDescription = null)
                            }
                        )
                        DropdownMenuItem(
                            text = { Text("Refresh") },
                            onClick = {
                                showMenu = false
                                viewModel.loadFiles(uiState.currentPath)
                            },
                            leadingIcon = {
                                Icon(Icons.Default.Refresh, contentDescription = null)
                            }
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            )
        },
        floatingActionButton = {
            if (!uiState.isUploading && !uiState.isDownloading) {
                FloatingActionButton(
                    onClick = { filePicker.launch("*/*") }
                ) {
                    Icon(Icons.Default.Add, contentDescription = "Upload File")
                }
            }
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
                        modifier = Modifier.align(Alignment.Center)
                    )
                }
                uiState.files.isEmpty() && !uiState.isLoading -> {
                    Column(
                        modifier = Modifier.align(Alignment.Center),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Folder,
                            contentDescription = null,
                            modifier = Modifier.size(64.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "No files here",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(8.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        items(uiState.files) { file ->
                            FileListItem(
                                file = file,
                                onFileClick = {
                                    if (file.isDirectory) {
                                        viewModel.navigateToFolder(file.name)
                                    }
                                },
                                onDeleteClick = {
                                    showDeleteDialog = file
                                }
                            )
                        }
                    }
                }
            }
            
            // Upload/Download Progress Overlay
            if (uiState.isUploading || uiState.isDownloading) {
                Card(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(16.dp)
                        .fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = if (uiState.isUploading) "Uploading..." else "Downloading...",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        
                        LinearProgressIndicator(
                            progress = { if (uiState.isUploading) uiState.uploadProgress else uiState.downloadProgress },
                            modifier = Modifier.fillMaxWidth()
                        )
                        
                        Text(
                            text = "${((if (uiState.isUploading) uiState.uploadProgress else uiState.downloadProgress) * 100).toInt()}%",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
            
            // Error Snackbar
            uiState.error?.let { error ->
                Snackbar(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(16.dp),
                    action = {
                        TextButton(onClick = { viewModel.clearError() }) {
                            Text("Dismiss")
                        }
                    }
                ) {
                    Text(error)
                }
            }
        }
    }
    
    // Delete Confirmation Dialog
    showDeleteDialog?.let { file ->
        AlertDialog(
            onDismissRequest = { showDeleteDialog = null },
            title = { Text("Delete ${file.name}?") },
            text = { 
                Text(
                    if (file.isDirectory) {
                        "This will delete the folder and all its contents. This action cannot be undone."
                    } else {
                        "This action cannot be undone."
                    }
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val fullPath = if (uiState.currentPath.isEmpty()) {
                            file.name
                        } else {
                            "${uiState.currentPath}/${file.name}"
                        }
                        viewModel.deleteFile(fullPath)
                        showDeleteDialog = null
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Delete")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = null }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@Composable
private fun FileListItem(
    file: FileItem,
    onFileClick: () -> Unit,
    onDeleteClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showMenu by remember { mutableStateOf(false) }
    
    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onFileClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                imageVector = when {
                    file.isDirectory -> Icons.Default.Folder
                    file.name.endsWith(".pdf") -> Icons.Default.Description
                    file.name.endsWith(".jpg") || file.name.endsWith(".png") -> Icons.Default.Image
                    file.name.endsWith(".mp4") || file.name.endsWith(".avi") -> Icons.Default.VideoFile
                    else -> Icons.Default.InsertDriveFile
                },
                contentDescription = null,
                modifier = Modifier.size(40.dp),
                tint = if (file.isDirectory) 
                    MaterialTheme.colorScheme.primary 
                else 
                    MaterialTheme.colorScheme.onSurfaceVariant
            )
            
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text(
                    text = file.name,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    if (!file.isDirectory) {
                        Text(
                            text = formatFileSize(file.size),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "•",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Text(
                        text = formatDate(file.modifiedAt),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            
            Box {
                IconButton(onClick = { showMenu = true }) {
                    Icon(
                        imageVector = Icons.Default.MoreVert,
                        contentDescription = "More options"
                    )
                }
                
                DropdownMenu(
                    expanded = showMenu,
                    onDismissRequest = { showMenu = false }
                ) {
                    DropdownMenuItem(
                        text = { Text("Delete") },
                        onClick = {
                            showMenu = false
                            onDeleteClick()
                        },
                        leadingIcon = {
                            Icon(
                                Icons.Default.Delete,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.error
                            )
                        }
                    )
                }
            }
        }
    }
}

private fun formatFileSize(bytes: Long): String {
    return when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        bytes < 1024 * 1024 * 1024 -> "${bytes / (1024 * 1024)} MB"
        else -> "${bytes / (1024 * 1024 * 1024)} GB"
    }
}

private fun formatDate(timestamp: Long): String {
    val sdf = SimpleDateFormat("MMM dd, yyyy", Locale.getDefault())
    return sdf.format(Date(timestamp * 1000))
}

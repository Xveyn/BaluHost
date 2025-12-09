package com.baluhost.android.presentation.ui.screens.files

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.presentation.ui.components.GlassCard
import com.baluhost.android.presentation.ui.components.GlassIntensity
import com.baluhost.android.presentation.ui.components.GradientButton
import com.baluhost.android.presentation.ui.theme.*
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
    onNavigateToSettings: () -> Unit = {},
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
    
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                brush = Brush.verticalGradient(
                    colors = listOf(Slate950, Slate900)
                )
            )
    ) {
        Scaffold(
            containerColor = androidx.compose.ui.graphics.Color.Transparent,
            topBar = {
                TopAppBar(
                    title = { 
                        Column {
                            Text(
                                "Dateien",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                                color = Slate100
                            )
                            if (uiState.currentPath.isNotEmpty()) {
                                Text(
                                    text = "/${uiState.currentPath}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Slate400
                                )
                            }
                        }
                    },
                    navigationIcon = {
                        if (uiState.currentPath.isNotEmpty()) {
                            IconButton(onClick = { viewModel.navigateBack() }) {
                                Icon(
                                    imageVector = Icons.Default.ArrowBack,
                                    contentDescription = "Zurück",
                                    tint = Sky400
                                )
                            }
                        }
                    },
                    actions = {
                        IconButton(onClick = { showMenu = true }) {
                            Icon(
                                imageVector = Icons.Default.Menu,
                                contentDescription = "Menü",
                                tint = Sky400
                            )
                        }
                        DropdownMenu(
                            expanded = showMenu,
                            onDismissRequest = { showMenu = false }
                        ) {
                            DropdownMenuItem(
                                text = { Text("VPN-Einstellungen") },
                                onClick = {
                                    showMenu = false
                                    onNavigateToVpn()
                                },
                                leadingIcon = {
                                    Icon(Icons.Default.Lock, contentDescription = null)
                                }
                            )
                            DropdownMenuItem(
                                text = { Text("Einstellungen") },
                                onClick = {
                                    showMenu = false
                                    onNavigateToSettings()
                                },
                                leadingIcon = {
                                    Icon(Icons.Default.Settings, contentDescription = null)
                                }
                            )
                            DropdownMenuItem(
                                text = { Text("Aktualisieren") },
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
                        containerColor = androidx.compose.ui.graphics.Color.Transparent
                    )
                )
            },
            floatingActionButton = {
                if (!uiState.isUploading && !uiState.isDownloading) {
                    FloatingActionButton(
                        onClick = { filePicker.launch("*/*") },
                        containerColor = Sky400,
                        contentColor = Slate950
                    ) {
                        Icon(Icons.Default.Add, contentDescription = "Datei hochladen")
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
                            modifier = Modifier.align(Alignment.Center),
                            color = Sky400
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
                                modifier = Modifier.size(80.dp),
                                tint = Slate600
                            )
                            Text(
                                text = "Keine Dateien vorhanden",
                                style = MaterialTheme.typography.bodyLarge,
                                color = Slate400
                            )
                        }
                    }
                    else -> {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(uiState.files) { file ->
                                GlassFileListItem(
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
                    GlassCard(
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(16.dp)
                            .fillMaxWidth(),
                        intensity = GlassIntensity.Heavy
                    ) {
                        Text(
                            text = if (uiState.isUploading) "Hochladen..." else "Herunterladen...",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = Slate100
                        )
                        
                        Spacer(modifier = Modifier.height(8.dp))
                        
                        LinearProgressIndicator(
                            progress = { if (uiState.isUploading) uiState.uploadProgress else uiState.downloadProgress },
                            modifier = Modifier.fillMaxWidth(),
                            color = Sky400,
                            trackColor = Slate700
                        )
                        
                        Spacer(modifier = Modifier.height(4.dp))
                        
                        Text(
                            text = "${((if (uiState.isUploading) uiState.uploadProgress else uiState.downloadProgress) * 100).toInt()}%",
                            style = MaterialTheme.typography.bodyMedium,
                            color = Slate400
                        )
                    }
                }
                
                // Error Snackbar
                uiState.error?.let { error ->
                    Snackbar(
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(16.dp),
                        containerColor = Red500,
                        contentColor = androidx.compose.ui.graphics.Color.White,
                        action = {
                            TextButton(onClick = { viewModel.clearError() }) {
                                Text("OK", color = androidx.compose.ui.graphics.Color.White)
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
                title = { 
                    Text(
                        "${file.name} löschen?",
                        fontWeight = FontWeight.Bold
                    ) 
                },
                text = { 
                    Text(
                        if (file.isDirectory) {
                            "Dadurch werden der Ordner und alle seine Inhalte gelöscht. Diese Aktion kann nicht rückgängig gemacht werden."
                        } else {
                            "Diese Aktion kann nicht rückgängig gemacht werden."
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
                            contentColor = Red500
                        )
                    ) {
                        Text("Löschen")
                    }
                },
                dismissButton = {
                    TextButton(onClick = { showDeleteDialog = null }) {
                        Text("Abbrechen")
                    }
                }
            )
        }
    }
}

@Composable
private fun GlassFileListItem(
    file: FileItem,
    onFileClick: () -> Unit,
    onDeleteClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showMenu by remember { mutableStateOf(false) }
    
    GlassCard(
        modifier = modifier.fillMaxWidth(),
        onClick = onFileClick,
        intensity = GlassIntensity.Medium,
        padding = PaddingValues(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
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
                tint = if (file.isDirectory) Sky400 else Indigo400
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
                    overflow = TextOverflow.Ellipsis,
                    color = Slate100
                )
                
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    if (!file.isDirectory) {
                        Text(
                            text = formatFileSize(file.size),
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate400
                        )
                        Text(
                            text = "•",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate400
                        )
                    }
                    Text(
                        text = formatDate(file.modifiedAt.epochSecond),
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400
                    )
                }
            }
            
            Box {
                IconButton(onClick = { showMenu = true }) {
                    Icon(
                        imageVector = Icons.Default.MoreVert,
                        contentDescription = "Weitere Optionen",
                        tint = Slate400
                    )
                }
                
                DropdownMenu(
                    expanded = showMenu,
                    onDismissRequest = { showMenu = false }
                ) {
                    DropdownMenuItem(
                        text = { Text("Löschen") },
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

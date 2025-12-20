package com.baluhost.android.presentation.ui.screens.files

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.presentation.ui.components.GlassCard
import com.baluhost.android.presentation.ui.components.GlassIntensity
import com.baluhost.android.presentation.ui.components.GradientButton
import com.baluhost.android.presentation.ui.components.OfflineBanner
import com.baluhost.android.presentation.ui.components.VpnStatusBanner
import com.baluhost.android.presentation.ui.theme.*
import com.google.accompanist.swiperefresh.SwipeRefresh
import com.google.accompanist.swiperefresh.rememberSwipeRefreshState
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

/**
 * Files Screen - Main file browser.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun FilesScreen(
    onNavigateToVpn: () -> Unit,
    onNavigateToSettings: () -> Unit = {},
    onNavigateToPendingOperations: () -> Unit = {},
    onNavigateToMediaViewer: (fileUrl: String, fileName: String, mimeType: String?) -> Unit = { _, _, _ -> },
    viewModel: FilesViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    var showDeleteDialog by remember { mutableStateOf<FileItem?>(null) }
    var showFolderPicker by remember { mutableStateOf(false) }
    var showMenu by remember { mutableStateOf(false) }
    val snackbarHostState = remember { SnackbarHostState() }
    
    // Collect VPN state for banner
    val isInHomeNetwork by viewModel.isInHomeNetwork.collectAsState()
    val hasVpnConfig by viewModel.hasVpnConfig.collectAsState()
    val vpnBannerDismissed by viewModel.vpnBannerDismissed.collectAsState()
    
    // Observe app lifecycle to trigger server check on resume
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.onAppResume()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }
    
    // Show offline warning when losing connection
    LaunchedEffect(uiState.isOnline) {
        if (!uiState.isOnline) {
            snackbarHostState.showSnackbar(
                message = "Keine Internetverbindung",
                duration = SnackbarDuration.Short
            )
        }
    }
    
    // File picker for upload
    val filePicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let {
            try {
                // Get original filename from URI
                val originalFileName = context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                    val nameIndex = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                    if (cursor.moveToFirst() && nameIndex != -1) {
                        cursor.getString(nameIndex)
                    } else {
                        null
                    }
                } ?: "upload_${System.currentTimeMillis()}"
                
                val inputStream = context.contentResolver.openInputStream(it)
                val tempFile = File(context.cacheDir, originalFileName)
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
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()  // Push content below system status bar
        ) {
            // Offline Banner below status bar
            OfflineBanner(isOnline = uiState.isOnline)
            
            // VPN Status Banner (shows when outside home network)
            VpnStatusBanner(
                isInHomeNetwork = isInHomeNetwork,
                hasVpnConfig = hasVpnConfig,
                onConnectVpn = onNavigateToVpn,
                onDismiss = { viewModel.dismissVpnBanner() },
                isDismissed = vpnBannerDismissed
            )
            
            Scaffold(
                containerColor = androidx.compose.ui.graphics.Color.Transparent,
                snackbarHost = { SnackbarHost(snackbarHostState) },
                modifier = Modifier.weight(1f),
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
                        // Selection mode toggle
                        if (!uiState.isSelectionMode) {
                            IconButton(onClick = { viewModel.toggleSelectionMode() }) {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = "Auswählen",
                                    tint = Sky400
                                )
                            }
                        }
                        
                        // Pending operations badge
                        if (uiState.pendingOperationsCount > 0) {
                            BadgedBox(
                                badge = {
                                    Badge(
                                        containerColor = if (uiState.isOnline) Sky400 else Red500,
                                        contentColor = Slate950
                                    ) {
                                        Text("${uiState.pendingOperationsCount}")
                                    }
                                }
                            ) {
                                IconButton(onClick = onNavigateToPendingOperations) {
                                    Icon(
                                        imageVector = Icons.Default.Sync,
                                        contentDescription = "Ausstehende Operationen",
                                        tint = Sky400
                                    )
                                }
                            }
                        }
                        
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
                // Show FAB only when NOT in selection mode
                if (!uiState.isSelectionMode && !uiState.isUploading && !uiState.isDownloading) {
                    FloatingActionButton(
                        onClick = { 
                            if (uiState.isOnline) {
                                filePicker.launch("*/*")
                            }
                        },
                        containerColor = if (uiState.isOnline) Sky400 else Slate600,
                        contentColor = if (uiState.isOnline) Slate950 else Slate400
                    ) {
                        Icon(
                            Icons.Default.Add, 
                            contentDescription = if (uiState.isOnline) "Datei hochladen" else "Offline - Upload nicht möglich"
                        )
                    }
                }
            }
        ) { paddingValues ->
            SwipeRefresh(
                state = rememberSwipeRefreshState(uiState.isRefreshing),
                onRefresh = { viewModel.refreshFiles() },
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
            ) {
                Box(modifier = Modifier.fillMaxSize()) {
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
                            // Bulk Action Bar (when in selection mode)
                            if (uiState.isSelectionMode) {
                                BulkActionBar(
                                    selectedCount = uiState.selectedFiles.size,
                                    onSelectAll = { viewModel.selectAll() },
                                    onDeselectAll = { viewModel.deselectAll() },
                                    onDelete = { 
                                        // Show confirmation dialog first
                                        showDeleteDialog = uiState.selectedFiles.firstOrNull() 
                                    },
                                    onDownload = { viewModel.downloadSelectedFiles() },
                                    onMove = { showFolderPicker = true },
                                    onCancel = { viewModel.toggleSelectionMode() }
                                )
                            }
                            
                            LazyColumn(
                                modifier = Modifier.fillMaxSize(),
                                contentPadding = PaddingValues(16.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                items(uiState.files) { file ->
                                    GlassFileListItem(
                                        file = file,
                                        isSelectionMode = uiState.isSelectionMode,
                                        isSelected = file in uiState.selectedFiles,
                                        onFileClick = {
                                            if (uiState.isSelectionMode) {
                                                // In selection mode, clicking toggles selection
                                                viewModel.toggleFileSelection(file)
                                            } else {
                                                // Normal click behavior
                                                android.util.Log.d("FilesScreen", "Clicked file: ${file.name}, mimeType: ${file.mimeType}, isDirectory: ${file.isDirectory}")
                                                
                                                when {
                                                    file.isDirectory -> {
                                                        viewModel.navigateToFolder(file.name)
                                                    }
                                                    file.mimeType?.startsWith("image/") == true ||
                                                    file.mimeType?.startsWith("video/") == true ||
                                                    file.mimeType?.startsWith("audio/") == true -> {
                                                        // Open media viewer for images, videos, audio
                                                        android.util.Log.d("FilesScreen", "Opening media viewer for ${file.name}")
                                                        val fileUrl = viewModel.getFileDownloadUrl(file.path)
                                                        android.util.Log.d("FilesScreen", "fileUrl = $fileUrl")
                                                        onNavigateToMediaViewer(fileUrl, file.name, file.mimeType)
                                                    }
                                                    else -> {
                                                        android.util.Log.d("FilesScreen", "Unknown file type for ${file.name}, mimeType: ${file.mimeType}")
                                                    }
                                                }
                                            }
                                        },
                                        onDeleteClick = {
                                            showDeleteDialog = file
                                        },
                                        onLongClick = {
                                            // Long-click to enter selection mode
                                            if (!uiState.isSelectionMode) {
                                                viewModel.toggleSelectionMode()
                                                viewModel.toggleFileSelection(file)
                                            }
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
                }  // Close Box
            }  // Close SwipeRefresh
        }  // Close Scaffold
        }  // Close Column
        
        // Delete Confirmation Dialog
        showDeleteDialog?.let { file ->
            val selectedFiles = uiState.selectedFiles
            val isBulkDelete = selectedFiles.isNotEmpty()
            val deleteCount = if (isBulkDelete) selectedFiles.size else 1
            
            AlertDialog(
                onDismissRequest = { showDeleteDialog = null },
                title = { 
                    Text(
                        if (isBulkDelete) {
                            "$deleteCount Dateien löschen?"
                        } else {
                            "${file.name} löschen?"
                        },
                        fontWeight = FontWeight.Bold
                    ) 
                },
                text = { 
                    Text(
                        if (isBulkDelete) {
                            "$deleteCount Dateien werden gelöscht. Diese Aktion kann nicht rückgängig gemacht werden."
                        } else if (file.isDirectory) {
                            "Dadurch werden der Ordner und alle seine Inhalte gelöscht. Diese Aktion kann nicht rückgängig gemacht werden."
                        } else {
                            "Diese Aktion kann nicht rückgängig gemacht werden."
                        }
                    )
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            if (isBulkDelete) {
                                viewModel.deleteSelectedFiles()
                            } else {
                                val fullPath = if (uiState.currentPath.isEmpty()) {
                                    file.name
                                } else {
                                    "${uiState.currentPath}/${file.name}"
                                }
                                viewModel.deleteFile(fullPath)
                            }
                            showDeleteDialog = null
                        }
                    ) {
                        Text("Löschen", color = Red400)
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
    
    // Folder Picker Dialog for move operation
    if (showFolderPicker) {
        FolderPickerDialog(
            currentPath = uiState.currentPath,
            folders = uiState.files.filter { it.isDirectory },
            onDismiss = { showFolderPicker = false },
            onFolderSelected = { destinationPath ->
                viewModel.moveSelectedFiles(destinationPath)
                showFolderPicker = false
            }
        )
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun GlassFileListItem(
    file: FileItem,
    isSelectionMode: Boolean = false,
    isSelected: Boolean = false,
    onFileClick: () -> Unit,
    onDeleteClick: () -> Unit,
    onLongClick: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    var showMenu by remember { mutableStateOf(false) }
    
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .combinedClickable(
                onClick = onFileClick,
                onLongClick = onLongClick
            )
            .clip(RoundedCornerShape(12.dp))
            .border(
                width = 1.dp,
                color = com.baluhost.android.presentation.ui.theme.Slate700.copy(alpha = if (isSelected) 0.7f else 0.5f),
                shape = RoundedCornerShape(12.dp)
            ),
        color = if (isSelected) 
            com.baluhost.android.presentation.ui.theme.Slate800.copy(alpha = 0.6f)
        else 
            com.baluhost.android.presentation.ui.theme.GlassMedium,
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Checkbox in selection mode
            if (isSelectionMode) {
                Checkbox(
                    checked = isSelected,
                    onCheckedChange = { onFileClick() },
                    colors = CheckboxDefaults.colors(
                        checkedColor = Sky400,
                        uncheckedColor = Slate400
                    )
                )
            }
            
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

/**
 * Bulk Action Bar shown when files are selected.
 */
@Composable
fun BulkActionBar(
    selectedCount: Int,
    onSelectAll: () -> Unit,
    onDeselectAll: () -> Unit,
    onDelete: () -> Unit,
    onDownload: () -> Unit,
    onMove: () -> Unit,
    onCancel: () -> Unit
) {
    GlassCard(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        intensity = GlassIntensity.Medium
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Selection count
            Text(
                text = "$selectedCount ausgewählt",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Sky400
            )
            
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                // Select All / Deselect All
                IconButton(onClick = if (selectedCount > 0) onDeselectAll else onSelectAll) {
                    Icon(
                        imageVector = if (selectedCount > 0) Icons.Default.CheckCircle else Icons.Default.CheckCircleOutline,
                        contentDescription = if (selectedCount > 0) "Alle abwählen" else "Alle auswählen",
                        tint = Slate300
                    )
                }
                
                // Download
                if (selectedCount > 0) {
                    IconButton(onClick = onDownload) {
                        Icon(
                            imageVector = Icons.Default.Download,
                            contentDescription = "Herunterladen",
                            tint = Sky400
                        )
                    }
                }
                
                // Move
                if (selectedCount > 0) {
                    IconButton(onClick = onMove) {
                        Icon(
                            imageVector = Icons.Default.DriveFileMove,
                            contentDescription = "Verschieben",
                            tint = Sky400
                        )
                    }
                }
                
                // Delete
                if (selectedCount > 0) {
                    IconButton(onClick = onDelete) {
                        Icon(
                            imageVector = Icons.Default.Delete,
                            contentDescription = "Löschen",
                            tint = Red400
                        )
                    }
                }
                
                // Cancel
                IconButton(onClick = onCancel) {
                    Icon(
                        imageVector = Icons.Default.Close,
                        contentDescription = "Abbrechen",
                        tint = Slate400
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

/**
 * Folder Picker Dialog for selecting destination folder for move operation.
 */
@Composable
fun FolderPickerDialog(
    currentPath: String,
    folders: List<FileItem>,
    onDismiss: () -> Unit,
    onFolderSelected: (String) -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "Zielordner wählen",
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "Wähle einen Zielordner für die ausgewählten Dateien:",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                
                Divider(modifier = Modifier.padding(vertical = 8.dp))
                
                // Root folder option
                TextButton(
                    onClick = { onFolderSelected("") },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Start,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Default.Home,
                            contentDescription = null,
                            tint = Sky400
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Text(
                            text = "/ (Root)",
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                }
                
                // Current folder option (if not in root)
                if (currentPath.isNotEmpty()) {
                    TextButton(
                        onClick = { onFolderSelected(currentPath) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.Start,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.FolderOpen,
                                contentDescription = null,
                                tint = Sky400
                            )
                            Spacer(modifier = Modifier.width(12.dp))
                            Text(
                                text = currentPath.ifEmpty { "/" },
                                style = MaterialTheme.typography.bodyLarge,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                }
                
                // Subfolders
                if (folders.isNotEmpty()) {
                    Text(
                        text = "Unterordner:",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                    
                    folders.forEach { folder ->
                        TextButton(
                            onClick = {
                                val folderPath = if (currentPath.isEmpty()) {
                                    folder.name
                                } else {
                                    "$currentPath/${folder.name}"
                                }
                                onFolderSelected(folderPath)
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.Start,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Folder,
                                    contentDescription = null,
                                    tint = Sky400
                                )
                                Spacer(modifier = Modifier.width(12.dp))
                                Text(
                                    text = folder.name,
                                    style = MaterialTheme.typography.bodyMedium
                                )
                            }
                        }
                    }
                } else if (currentPath.isEmpty()) {
                    Text(
                        text = "Keine Ordner verfügbar",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Abbrechen")
            }
        }
    )
}

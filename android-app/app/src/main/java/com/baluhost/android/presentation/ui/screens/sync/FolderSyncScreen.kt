package com.baluhost.android.presentation.ui.screens.sync

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.domain.model.sync.*
import com.baluhost.android.presentation.ui.theme.*
import com.baluhost.android.presentation.ui.components.*
import com.baluhost.android.util.PermissionHelper
import com.google.accompanist.swiperefresh.SwipeRefresh
import com.google.accompanist.swiperefresh.rememberSwipeRefreshState
import kotlinx.coroutines.delay

/**
 * Folder Sync Screen
 * Displays configured sync folders, upload queue, and allows adding new folders.
 * 
 * Best Practices Implemented:
 * - Pull-to-refresh for manual data update
 * - Storage permission handling for Android 11+
 * - Last sync timestamp prominently displayed
 * - Clear empty state with actionable guidance
 * - Smooth animations and glass morphism UI
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FolderSyncScreen(
    onNavigateBack: () -> Unit,
    viewModel: FolderSyncViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val pendingConflicts by viewModel.pendingConflicts.collectAsState()
    val context = LocalContext.current
    
    var showFolderPicker by remember { mutableStateOf(false) }
    var showConfigDialog by remember { mutableStateOf(false) }
    var showWebDavDialog by remember { mutableStateOf(false) }
    var showConflictDialog by remember { mutableStateOf(false) }
    var showPermissionDialog by remember { mutableStateOf(false) }
    var selectedFolder by remember { mutableStateOf<SyncFolderConfig?>(null) }
    var selectedFolderUri by remember { mutableStateOf<Uri?>(null) }
    var selectedFolderName by remember { mutableStateOf<String?>(null) }
    var isRefreshing by remember { mutableStateOf(false) }
    
    // Check storage permissions on first load
    LaunchedEffect(Unit) {
        if (!PermissionHelper.hasStoragePermissions(context)) {
            showPermissionDialog = true
        }
    }
    
    // Show conflict dialog when conflicts are detected
    LaunchedEffect(pendingConflicts) {
        if (pendingConflicts.isNotEmpty()) {
            showConflictDialog = true
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Ordner-Synchronisation") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.Default.ArrowBack,
                            contentDescription = "Zurück",
                            tint = Sky400
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { showWebDavDialog = true }) {
                        Icon(
                            imageVector = Icons.Default.Cloud, 
                            contentDescription = "WebDAV-Browser", 
                            tint = Sky400
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Slate900
                )
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { 
                    if (PermissionHelper.hasStoragePermissions(context)) {
                        showFolderPicker = true
                    } else {
                        showPermissionDialog = true
                    }
                },
                containerColor = Sky500,
                contentColor = Slate950
            ) {
                Icon(
                    imageVector = Icons.Default.Add,
                    contentDescription = "Ordner hinzufügen"
                )
            }
        },
        containerColor = Slate950
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            when (uiState) {
                is FolderSyncState.Loading -> {
                    CircularProgressIndicator(
                        modifier = Modifier.align(Alignment.Center),
                        color = Sky400
                    )
                }
                is FolderSyncState.Success -> {
                    val state = uiState as FolderSyncState.Success
                    
                    // Handle refresh state changes
                    LaunchedEffect(isRefreshing) {
                        if (isRefreshing) {
                            viewModel.loadSyncFolders()
                            delay(1000)  // Simulate network delay
                            isRefreshing = false
                        }
                    }
                    
                    SwipeRefresh(
                        state = rememberSwipeRefreshState(isRefreshing),
                        onRefresh = {
                            isRefreshing = true
                        }
                    ) {
                        SyncContent(
                            folders = state.folders,
                            uploadQueue = state.uploadQueue,
                            onFolderClick = { folder ->
                                selectedFolder = folder
                                showConfigDialog = true
                            },
                            onDeleteFolder = viewModel::deleteFolder,
                            onTriggerSync = viewModel::triggerSync,
                            onCancelUpload = viewModel::cancelUpload,
                            onRetryUpload = viewModel::retryUpload
                        )
                    }
                }
                is FolderSyncState.Error -> {
                    ErrorContent(
                        message = (uiState as FolderSyncState.Error).message,
                        onRetry = viewModel::loadSyncFolders
                    )
                }
            }
        }
    }
    
    // Folder picker dialog
    if (showFolderPicker) {
        FolderPickerDialog(
            onFolderSelected = { uri, name ->
                selectedFolderUri = uri
                selectedFolderName = name
                showFolderPicker = false
                showConfigDialog = true
            },
            onDismiss = { showFolderPicker = false }
        )
    }

    // WebDAV modal (inline)
    if (showWebDavDialog) {
        val webDavVm: com.baluhost.android.presentation.viewmodel.WebDavViewModel = hiltViewModel()
        var wdUsername by remember { mutableStateOf("") }
        var wdPassword by remember { mutableStateOf("") }
        var wdPath by remember { mutableStateOf("") }

        val wdListing by webDavVm.listing.collectAsState()
        val wdAuthOk by webDavVm.authOk.collectAsState()

        AlertDialog(
            onDismissRequest = { showWebDavDialog = false },
            title = { Text("WebDAV verbinden") },
            text = {
                Column(modifier = Modifier.fillMaxWidth()) {
                    OutlinedTextField(
                        value = wdUsername,
                        onValueChange = { wdUsername = it },
                        label = { Text("Benutzer") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(
                        value = wdPassword,
                        onValueChange = { wdPassword = it },
                        label = { Text("Passwort") },
                        visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(
                        value = wdPath,
                        onValueChange = { wdPath = it },
                        label = { Text("Remote Path (URL)") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { webDavVm.testCredentials(wdUsername.ifBlank { null }, wdPassword.ifBlank { null }) }) {
                            Text("Test Credentials")
                        }
                        Button(onClick = { webDavVm.listRemote(wdPath, wdUsername.ifBlank { null }, wdPassword.ifBlank { null }) }) {
                            Text("List")
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    wdAuthOk?.let { ok ->
                        if (ok) Text("Authentication successful", color = Color(0xFF2E7D32))
                        else Text("Authentication failed", color = Color(0xFFB00020))
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    if (wdListing.isNotEmpty()) {
                        LazyColumn(modifier = Modifier.heightIn(max = 200.dp)) {
                            items(wdListing) { item ->
                                Row(modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(8.dp)) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(item.name, color = Slate100)
                                        Text("${item.size} bytes", style = MaterialTheme.typography.bodySmall, color = Slate300)
                                    }
                                    Button(onClick = {
                                        // select this remote path and open config dialog
                                        selectedFolderUri = Uri.parse(item.uri)
                                        selectedFolderName = item.name
                                        showWebDavDialog = false
                                        showConfigDialog = true
                                    }) {
                                        Text("Select")
                                    }
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showWebDavDialog = false }) { Text("Close") }
            },
            dismissButton = {
                TextButton(onClick = { showWebDavDialog = false }) { Text("Cancel") }
            },
            containerColor = Slate900
        )
    }
    
    // Storage Permission Dialog
    if (showPermissionDialog) {
        val permissionLauncher = rememberLauncherForActivityResult(
            contract = ActivityResultContracts.RequestMultiplePermissions()
        ) { permissions ->
            val allGranted = permissions.values.all { it }
            if (allGranted) {
                showPermissionDialog = false
                showFolderPicker = true
            }
        }
        
        AlertDialog(
            onDismissRequest = { showPermissionDialog = false },
            icon = {
                Icon(
                    imageVector = Icons.Default.SecurityUpdateWarning,
                    contentDescription = null,
                    tint = Sky400,
                    modifier = Modifier.size(32.dp)
                )
            },
            title = { Text("Speicherzugriff erforderlich") },
            text = {
                Column(
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = PermissionHelper.getPermissionRationale(),
                        style = MaterialTheme.typography.bodyMedium,
                        color = Slate300
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        permissionLauncher.launch(PermissionHelper.getStoragePermissions())
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Sky500
                    )
                ) {
                    Text("Berechtigung erteilen")
                }
            },
            dismissButton = {
                TextButton(onClick = { showPermissionDialog = false }) {
                    Text("Später", color = Slate400)
                }
            },
            containerColor = Slate900,
            iconContentColor = Sky400,
            titleContentColor = Slate100,
            textContentColor = Slate300
        )
    }
    
    // Add Sync Folder dialog - simplified for new folder creation
    if (showConfigDialog && selectedFolder == null) {
        AddSyncFolderDialog(
            localFolderUri = selectedFolderUri,
            localFolderName = selectedFolderName,
            onDismiss = {
                showConfigDialog = false
                selectedFolderUri = null
                selectedFolderName = null
            },
            onConfirm = { localPath, remotePath, syncType, conflictResolution, autoSync ->
                viewModel.createFolder(
                    SyncFolderCreateConfig(
                        localUri = Uri.parse(localPath),
                        remotePath = remotePath,
                        syncType = syncType,
                        autoSync = autoSync,
                        conflictResolution = conflictResolution,
                        excludePatterns = emptyList(),
                        adapterType = "filesystem",
                        credentials = null,
                        saveCredentials = false
                    )
                )
                showConfigDialog = false
                selectedFolderUri = null
                selectedFolderName = null
            }
        )
    }
    
    // Edit Sync Folder dialog - for existing folders
    if (showConfigDialog && selectedFolder != null) {
        SyncFolderConfigDialog(
            folder = selectedFolder,
            folderUri = selectedFolderUri,
            folderName = selectedFolderName,
            onConfirm = { config ->
                viewModel.updateFolder(config as SyncFolderUpdateConfig)
                showConfigDialog = false
                selectedFolder = null
                selectedFolderUri = null
                selectedFolderName = null
            },
            onDismiss = {
                showConfigDialog = false
                selectedFolder = null
                selectedFolderUri = null
                selectedFolderName = null
            }
        )
    }
    
    // Conflict resolution dialog
    if (showConflictDialog && pendingConflicts.isNotEmpty()) {
        ConflictResolutionDialog(
            conflicts = pendingConflicts,
            onResolve = { resolutions ->
                // Get folder ID from first conflict (string prefix)
                val folderId = pendingConflicts.firstOrNull()?.id?.substringBefore('_')
                if (!folderId.isNullOrEmpty()) {
                    viewModel.resolveConflicts(folderId, resolutions)
                }
                showConflictDialog = false
            },
            onDismiss = {
                // Get folder ID from first conflict (string prefix)
                val folderId = pendingConflicts.firstOrNull()?.id?.substringBefore('_')
                if (!folderId.isNullOrEmpty()) {
                    viewModel.dismissConflicts(folderId)
                }
                showConflictDialog = false
            }
        )
    }
}

@Composable
private fun SyncContent(
    folders: List<SyncFolderConfig>,
    uploadQueue: List<UploadQueueItem>,
    onFolderClick: (SyncFolderConfig) -> Unit,
    onDeleteFolder: (String) -> Unit,
    onTriggerSync: (String) -> Unit,
    onCancelUpload: (String) -> Unit,
    onRetryUpload: (String) -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Summary Card - Last Sync and Status Overview
        item {
            SyncSummaryCard(folders = folders)
        }
        
        // Sync Folders Section
        item {
            Text(
                text = "Synchronisierte Ordner (${folders.size})",
                style = MaterialTheme.typography.titleLarge,
                color = Slate100,
                fontWeight = FontWeight.Bold
            )
        }
        
        if (folders.isEmpty()) {
            item {
                EmptySyncState()
            }
        } else {
            items(folders, key = { it.id }) { folder ->
                SyncFolderCard(
                    folder = folder,
                    onClick = { onFolderClick(folder) },
                    onDelete = { onDeleteFolder(folder.id) },
                    onSync = { onTriggerSync(folder.id) }
                )
            }
        }
        
        // Upload Queue Section
        if (uploadQueue.isNotEmpty()) {
            item {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Upload-Warteschlange (${uploadQueue.size})",
                    style = MaterialTheme.typography.titleMedium,
                    color = Slate100,
                    fontWeight = FontWeight.Bold
                )
            }
            
            items(uploadQueue, key = { it.id }) { item ->
                UploadQueueCard(
                    item = item,
                    onCancel = { onCancelUpload(item.id) },
                    onRetry = { onRetryUpload(item.id) }
                )
            }
        }
    }
}

/**
 * Summary card showing overall sync status and last sync time.
 */
@Composable
private fun SyncSummaryCard(folders: List<SyncFolderConfig>) {
    val lastSyncTime = folders.mapNotNull { it.lastSync }.maxOrNull()
    val activeSyncs = folders.count { it.syncStatus == SyncStatus.SYNCING }
    val errorCount = folders.count { it.syncStatus == SyncStatus.ERROR }
    
    GlassCard(intensity = GlassIntensity.Medium) {
        Column(
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Last Sync Time - Prominent Display
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Schedule,
                    contentDescription = null,
                    tint = Sky400,
                    modifier = Modifier.size(20.dp)
                )
                
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Letzter Sync",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400
                    )
                    Text(
                        text = if (lastSyncTime != null) {
                            formatTimestamp(lastSyncTime)
                        } else {
                            "Noch nicht synchronisiert"
                        },
                        style = MaterialTheme.typography.titleMedium,
                        color = Slate100,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            Divider(color = Slate700, modifier = Modifier.fillMaxWidth())
            
            // Status Summary
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Active Syncs
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.weight(1f)
                ) {
                    Badge(
                        containerColor = if (activeSyncs > 0) Sky400 else Slate700,
                        contentColor = Slate950
                    ) {
                        Text(
                            activeSyncs.toString(),
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Text(
                        text = "Aktiv",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
                
                // Total Folders
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.weight(1f)
                ) {
                    Badge(
                        containerColor = Green500,
                        contentColor = Slate950
                    ) {
                        Text(
                            folders.size.toString(),
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Text(
                        text = "Ordner",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
                
                // Errors
                if (errorCount > 0) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.weight(1f)
                    ) {
                        Badge(
                            containerColor = Red500,
                            contentColor = Slate950
                        ) {
                            Text(
                                errorCount.toString(),
                                fontWeight = FontWeight.Bold
                            )
                        }
                        Text(
                            text = "Fehler",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate400,
                            modifier = Modifier.padding(top = 4.dp)
                        )
                    }
                }
            }
        }
    }
}

/**
 * Empty state with guidance for adding first sync folder.
 */
@Composable
private fun EmptySyncState() {
    GlassCard(intensity = GlassIntensity.Light) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Icon(
                imageVector = Icons.Default.FolderOff,
                contentDescription = null,
                tint = Slate400,
                modifier = Modifier.size(56.dp)
            )
            
            Text(
                text = "Keine Ordner konfiguriert",
                style = MaterialTheme.typography.titleMedium,
                color = Slate200,
                fontWeight = FontWeight.Bold
            )
            
            Text(
                text = "Fügen Sie einen Ordner hinzu, um Dateien mit Ihrem NAS zu synchronisieren",
                style = MaterialTheme.typography.bodySmall,
                color = Slate400,
                textAlign = TextAlign.Center
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            // Tips
            Column(
                verticalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                listOf(
                    "Tippen Sie auf + um einen lokalen Ordner zu wählen",
                    "Geben Sie einen Pfad auf dem NAS ein",
                    "Wählen Sie die Synchronisationsart (Upload/Download/Bidirektional)"
                ).forEach { tip ->
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.Top
                    ) {
                        Text(
                            text = "•",
                            color = Sky400,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = tip,
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate400
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SyncFolderCard(
    folder: SyncFolderConfig,
    onClick: () -> Unit,
    onDelete: () -> Unit,
    onSync: () -> Unit
) {
    val statusColor = when (folder.syncStatus) {
        SyncStatus.IDLE -> Slate400
        SyncStatus.SYNCING -> Sky400
        SyncStatus.ERROR -> Red500
        SyncStatus.PAUSED -> Yellow500
    }
    
    val statusIcon = when (folder.syncStatus) {
        SyncStatus.IDLE -> Icons.Default.CheckCircle
        SyncStatus.SYNCING -> Icons.Default.Sync
        SyncStatus.ERROR -> Icons.Default.Error
        SyncStatus.PAUSED -> Icons.Default.Pause
    }
    
    var showDeleteDialog by remember { mutableStateOf(false) }
    
    GlassCard(
        intensity = GlassIntensity.Medium,
        onClick = onClick
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                imageVector = Icons.Default.Folder,
                contentDescription = null,
                tint = Sky400,
                modifier = Modifier.size(40.dp)
            )
            
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = folder.remotePath,
                    style = MaterialTheme.typography.titleMedium,
                    color = Slate100,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = folder.syncType.name.replace("_", " "),
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate300
                )
                if (folder.lastSync != null) {
                    Text(
                        text = "Letzte Sync: ${formatTimestamp(folder.lastSync)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400
                    )
                }
            }
            
            Icon(
                imageVector = statusIcon,
                contentDescription = folder.syncStatus.name,
                tint = statusColor,
                modifier = Modifier.size(24.dp)
            )
        }
        
        if (folder.syncStatus == SyncStatus.SYNCING && folder.totalFiles > 0) {
            Spacer(modifier = Modifier.height(12.dp))
            Column {
                Row(
                    horizontalArrangement = Arrangement.SpaceBetween,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = "Fortschritt",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate300
                    )
                    Text(
                        text = "${folder.syncedFiles}/${folder.totalFiles}",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate300
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
                LinearProgressIndicator(
                    progress = { folder.syncProgress },
                    modifier = Modifier.fillMaxWidth(),
                    color = Sky400,
                    trackColor = Slate700
                )
            }
        }
        
        Spacer(modifier = Modifier.height(12.dp))
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            OutlinedButton(
                onClick = onSync,
                enabled = folder.syncStatus != SyncStatus.SYNCING,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = Sky400
                )
            ) {
                Icon(
                    imageVector = Icons.Default.Sync,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text("Sync")
            }
            
            IconButton(
                onClick = { showDeleteDialog = true },
                colors = IconButtonDefaults.iconButtonColors(
                    contentColor = Red500
                )
            ) {
                Icon(
                    imageVector = Icons.Default.Delete,
                    contentDescription = "Löschen"
                )
            }
        }
    }
    
    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            icon = {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = null,
                    tint = Red500
                )
            },
            title = { Text("Ordner entfernen?") },
            text = {
                Text("Möchten Sie diesen Ordner wirklich aus der Synchronisation entfernen?")
            },
            confirmButton = {
                Button(
                    onClick = {
                        onDelete()
                        showDeleteDialog = false
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Red500
                    )
                ) {
                    Text("Entfernen")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) {
                    Text("Abbrechen")
                }
            },
            containerColor = Slate900
        )
    }
}

@Composable
private fun UploadQueueCard(
    item: UploadQueueItem,
    onCancel: () -> Unit,
    onRetry: () -> Unit
) {
    GlassCard(intensity = GlassIntensity.Light) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                imageVector = when (item.status) {
                    UploadStatus.PENDING -> Icons.Default.Schedule
                    UploadStatus.UPLOADING -> Icons.Default.Upload
                    UploadStatus.COMPLETED -> Icons.Default.CheckCircle
                    UploadStatus.FAILED -> Icons.Default.Error
                    UploadStatus.CANCELLED -> Icons.Default.Cancel
                },
                contentDescription = null,
                tint = when (item.status) {
                    UploadStatus.COMPLETED -> Green500
                    UploadStatus.FAILED -> Red500
                    UploadStatus.UPLOADING -> Sky400
                    else -> Slate400
                },
                modifier = Modifier.size(32.dp)
            )
            
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.fileName,
                    style = MaterialTheme.typography.bodyMedium,
                    color = Slate100,
                    fontWeight = FontWeight.SemiBold
                )
                Text(
                    text = formatBytes(item.fileSize),
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate400
                )
                
                if (item.status == UploadStatus.UPLOADING) {
                    Spacer(modifier = Modifier.height(4.dp))
                    LinearProgressIndicator(
                        progress = { item.progress },
                        modifier = Modifier.fillMaxWidth(),
                        color = Sky400,
                        trackColor = Slate700
                    )
                }
                
                if (item.errorMessage != null) {
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = item.errorMessage,
                        style = MaterialTheme.typography.bodySmall,
                        color = Red500
                    )
                }
            }
            
            when (item.status) {
                UploadStatus.UPLOADING, UploadStatus.PENDING -> {
                    IconButton(onClick = onCancel) {
                        Icon(
                            imageVector = Icons.Default.Cancel,
                            contentDescription = "Abbrechen",
                            tint = Red500
                        )
                    }
                }
                UploadStatus.FAILED -> {
                    if (item.canRetry) {
                        IconButton(onClick = onRetry) {
                            Icon(
                                imageVector = Icons.Default.Refresh,
                                contentDescription = "Wiederholen",
                                tint = Sky400
                            )
                        }
                    }
                }
                else -> {}
            }
        }
    }
}

@Composable
private fun ErrorContent(
    message: String,
    onRetry: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.Error,
            contentDescription = null,
            tint = Red500,
            modifier = Modifier.size(64.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = "Fehler",
            style = MaterialTheme.typography.titleLarge,
            color = Slate100,
            fontWeight = FontWeight.Bold
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = Slate400
        )
        Spacer(modifier = Modifier.height(24.dp))
        Button(
            onClick = onRetry,
            colors = ButtonDefaults.buttonColors(
                containerColor = Sky500
            )
        ) {
            Text("Erneut versuchen")
        }
    }
}

private fun formatTimestamp(timestamp: Long): String {
    val now = System.currentTimeMillis()
    val diff = now - timestamp
    
    return when {
        diff < 60_000 -> "Gerade eben"
        diff < 3_600_000 -> "${diff / 60_000} Min"
        diff < 86_400_000 -> "${diff / 3_600_000} Std"
        else -> "${diff / 86_400_000} Tage"
    }
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


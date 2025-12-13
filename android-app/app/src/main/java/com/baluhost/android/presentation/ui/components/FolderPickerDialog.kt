package com.baluhost.android.presentation.ui.components

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.baluhost.android.presentation.ui.theme.*

/**
 * Folder picker dialog using Storage Access Framework.
 * Requests persistent URI permissions for folder synchronization.
 */
@Composable
fun FolderPickerDialog(
    onFolderSelected: (Uri, String) -> Unit,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    var selectedFolderUri by remember { mutableStateOf<Uri?>(null) }
    var selectedFolderName by remember { mutableStateOf<String?>(null) }
    
    val folderPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocumentTree()
    ) { uri: Uri? ->
        uri?.let {
            // Request persistent permissions
            val takeFlags = Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            
            try {
                context.contentResolver.takePersistableUriPermission(uri, takeFlags)
                
                // Get folder name
                val documentFile = androidx.documentfile.provider.DocumentFile.fromTreeUri(context, uri)
                val folderName = documentFile?.name ?: "Unknown Folder"
                
                selectedFolderUri = uri
                selectedFolderName = folderName
            } catch (e: Exception) {
                // Permission grant failed
                selectedFolderUri = null
                selectedFolderName = null
            }
        }
    }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = {
            Icon(
                imageVector = Icons.Default.Folder,
                contentDescription = null,
                tint = Sky400,
                modifier = Modifier.size(32.dp)
            )
        },
        title = {
            Text(
                text = "Ordner auswählen",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text(
                    text = "Wählen Sie einen Ordner aus, der mit dem NAS synchronisiert werden soll.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Slate300
                )
                
                if (selectedFolderName != null) {
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
                                    text = "Ausgewählt:",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Slate400
                                )
                                Text(
                                    text = selectedFolderName ?: "",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = Slate100,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                        }
                    }
                }
                
                Button(
                    onClick = { folderPickerLauncher.launch(null) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Sky500
                    )
                ) {
                    Icon(
                        imageVector = Icons.Default.Folder,
                        contentDescription = null,
                        modifier = Modifier.size(20.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Ordner durchsuchen")
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    selectedFolderUri?.let { uri ->
                        selectedFolderName?.let { name ->
                            onFolderSelected(uri, name)
                        }
                    }
                },
                enabled = selectedFolderUri != null,
                colors = ButtonDefaults.buttonColors(
                    containerColor = Green500
                )
            ) {
                Text("Bestätigen")
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

/**
 * Permission request dialog for storage access.
 */
@Composable
fun StoragePermissionDialog(
    onRequestPermission: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = {
            Icon(
                imageVector = Icons.Default.Folder,
                contentDescription = null,
                tint = Yellow500,
                modifier = Modifier.size(32.dp)
            )
        },
        title = {
            Text(
                text = "Speicherzugriff erforderlich",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Text(
                text = "Um Ordner zu synchronisieren, benötigt BaluHost Zugriff auf Ihren Gerätespeicher. Sie können die Berechtigungen in den Einstellungen jederzeit widerrufen.",
                style = MaterialTheme.typography.bodyMedium,
                color = Slate300
            )
        },
        confirmButton = {
            Button(
                onClick = onRequestPermission,
                colors = ButtonDefaults.buttonColors(
                    containerColor = Sky500
                )
            ) {
                Text("Berechtigung erteilen")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Abbrechen", color = Slate300)
            }
        },
        containerColor = Slate900,
        iconContentColor = Yellow500,
        titleContentColor = Slate100,
        textContentColor = Slate300
    )
}


package com.baluhost.android.presentation.ui.screens.permissions

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Save
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import com.baluhost.android.data.remote.dto.FilePermissionRuleDto

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PermissionsScreen(viewModel: PermissionsViewModel = hiltViewModel()) {
    val path by viewModel.path.collectAsState()
    val rules by viewModel.rules.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()

    var newUserIdText by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Berechtigungen verwalten") },
                actions = {
                    IconButton(onClick = { viewModel.savePermissions() }) {
                        Icon(Icons.Default.Save, contentDescription = "Speichern")
                    }
                }
            )
        }
    ) { padding ->
        Column(modifier = Modifier
            .fillMaxSize()
            .padding(padding)
            .padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {

            OutlinedTextField(
                value = path,
                onValueChange = { viewModel.setPath(it) },
                label = { Text("Pfad (z.B. /documents/report.pdf)") },
                modifier = Modifier.fillMaxWidth()
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { viewModel.loadPermissions() }) { Text("Laden") }
                OutlinedTextField(
                    value = newUserIdText,
                    onValueChange = { newUserIdText = it.filter { ch -> ch.isDigit() } },
                    label = { Text("User ID hinzufügen") },
                    modifier = Modifier.weight(1f)
                )
                IconButton(onClick = {
                    newUserIdText.toIntOrNull()?.let { id ->
                        viewModel.addRule(id)
                        newUserIdText = ""
                    }
                }) { Icon(Icons.Default.Add, contentDescription = "Add") }
            }

            if (loading) {
                Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }

            error?.let { msg ->
                Text(text = msg, color = MaterialTheme.colorScheme.error)
            }

            LazyColumn(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                itemsIndexed(rules) { idx, rule ->
                    PermissionRow(rule = rule, onToggle = { v, e, d -> viewModel.toggleRule(idx, v, e, d) })
                }
            }
        }
    }
}

@Composable
fun PermissionRow(rule: FilePermissionRuleDto, onToggle: (Boolean?, Boolean?, Boolean?) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = "User ID: ${rule.userId}")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(text = "View")
                    Switch(checked = rule.canView, onCheckedChange = { onToggle(it, null, null) })
                    Text(text = "Edit")
                    Switch(checked = rule.canEdit, onCheckedChange = { onToggle(null, it, null) })
                    Text(text = "Delete")
                    Switch(checked = rule.canDelete, onCheckedChange = { onToggle(null, null, it) })
                }
            }
        }
    }
}

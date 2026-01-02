package com.baluhost.android.presentation.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.presentation.viewmodel.WebDavViewModel

@Composable
fun WebDavScreen(viewModel: WebDavViewModel = hiltViewModel()) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var path by remember { mutableStateOf("") }

    val listing by viewModel.listing.collectAsState()
    val authOk by viewModel.authOk.collectAsState()

    Column(modifier = Modifier
        .fillMaxSize()
        .padding(16.dp)) {

        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("Username") },
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = path,
            onValueChange = { path = it },
            label = { Text("Remote path (URL)") },
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(12.dp))

        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { viewModel.testCredentials(username.ifBlank { null }, password.ifBlank { null }) }) {
                Text("Test Credentials")
            }
            Button(onClick = { viewModel.listRemote(path, username.ifBlank { null }, password.ifBlank { null }) }) {
                Text("List")
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        authOk?.let { ok ->
            if (ok) Text("Authentication successful", color = Color(0xFF2E7D32))
            else Text("Authentication failed", color = Color(0xFFB00020))
        }

        Spacer(modifier = Modifier.height(12.dp))

        LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
            items(listing) { item ->
                Text(text = "${item.name} — ${item.size} bytes")
                Spacer(modifier = Modifier.height(6.dp))
            }
        }
    }
}

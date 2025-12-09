package com.baluhost.android.presentation.ui.screens.lock

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.LifecycleResumeEffect

/**
 * Lock screen shown when app resumes after timeout or on demand.
 * Supports both biometric and PIN authentication.
 */
@Composable
fun LockScreen(
    onUnlocked: () -> Unit,
    viewModel: LockScreenViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    val activity = context as? FragmentActivity
    
    var pin by remember { mutableStateOf("") }
    var showError by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf("") }
    
    // Auto-trigger biometric on screen appear
    LaunchedEffect(Unit) {
        if (uiState.biometricAvailable && activity != null) {
            viewModel.authenticateBiometric(activity)
        }
    }
    
    // Handle unlock success
    LaunchedEffect(uiState.isUnlocked) {
        if (uiState.isUnlocked) {
            onUnlocked()
        }
    }
    
    // Handle authentication errors
    LaunchedEffect(uiState.error) {
        uiState.error?.let { error ->
            errorMessage = error
            showError = true
        }
    }
    
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        Box(
            modifier = Modifier.fillMaxSize()
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
            // Lock icon
            Icon(
                imageVector = Icons.Default.Lock,
                contentDescription = null,
                modifier = Modifier.size(80.dp),
                tint = MaterialTheme.colorScheme.primary
            )
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Title
            Text(
                text = "BaluHost ist gesperrt",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            // Subtitle
            Text(
                text = "Entsperren Sie die App, um fortzufahren",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center
            )
            
            Spacer(modifier = Modifier.height(48.dp))
            
            // Biometric authentication button
            if (uiState.biometricAvailable && activity != null) {
                Button(
                    onClick = { viewModel.authenticateBiometric(activity) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                    enabled = !uiState.isAuthenticating
                ) {
                    if (uiState.isAuthenticating) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            color = Color.White,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Icon(
                            imageVector = Icons.Default.Fingerprint,
                            contentDescription = null,
                            modifier = Modifier.size(24.dp)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Text("Mit Biometrie entsperren")
                    }
                }
                
                if (uiState.pinAvailable) {
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    Text(
                        text = "oder",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    
                    Spacer(modifier = Modifier.height(16.dp))
                }
            }
            
            // PIN authentication
            if (uiState.pinAvailable) {
                OutlinedTextField(
                    value = pin,
                    onValueChange = { 
                        if (it.length <= 8 && it.all { c -> c.isDigit() }) {
                            pin = it
                            showError = false
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("PIN eingeben") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    singleLine = true,
                    isError = showError,
                    supportingText = if (showError) {
                        { Text(errorMessage, color = MaterialTheme.colorScheme.error) }
                    } else null,
                    leadingIcon = {
                        Icon(Icons.Default.Pin, contentDescription = null)
                    }
                )
                
                Spacer(modifier = Modifier.height(16.dp))
                
                Button(
                    onClick = {
                        val success = viewModel.authenticatePin(pin)
                        if (!success) {
                            showError = true
                            errorMessage = "Falsche PIN"
                            pin = ""
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                    enabled = pin.length >= 4
                ) {
                    Icon(
                        imageVector = Icons.Default.Check,
                        contentDescription = null
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Entsperren")
                }
            }
            
            // No authentication method available
            if (!uiState.biometricAvailable && !uiState.pinAvailable) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = "Keine Authentifizierungsmethode verfügbar",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.error
                        )
                        Text(
                            text = "Bitte richten Sie eine Biometrie oder PIN in den Einstellungen ein.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
            }
            } // End of Column
            
            // Error Snackbar at bottom of Box
            if (showError && errorMessage.isNotEmpty()) {
                Snackbar(
                    modifier = Modifier
                        .padding(16.dp)
                        .align(Alignment.BottomCenter),
                    action = {
                        TextButton(onClick = { showError = false }) {
                            Text("OK")
                        }
                    }
                ) {
                    Text(errorMessage)
                }
            }
        } // End of Box
    }
}

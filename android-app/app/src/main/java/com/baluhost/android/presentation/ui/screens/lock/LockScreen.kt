package com.baluhost.android.presentation.ui.screens.lock

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Backspace
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
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
 * 
 * SECURITY: Back button and gestures are disabled to prevent bypass.
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
    
    // SECURITY: Block back button and back gestures
    // User MUST authenticate to proceed
    BackHandler(enabled = true) {
        // Do nothing - back button is disabled on lock screen
    }
    
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
    
    // Gradient background matching web design - enhanced version
    val gradientBrush = Brush.linearGradient(
        colors = listOf(
            Color(0xFF1e293b), // slate-800
            Color(0xFF1e1b4b), // indigo-950
            Color(0xFF0f172a), // slate-900
            Color(0xFF1e1b4b), // indigo-950
            Color(0xFF0c0a1f), // very dark violet
            Color(0xFF020617)  // slate-950
        ),
        start = Offset(0f, 0f),
        end = Offset(1000f, 1200f) // 135deg diagonal
    )
    
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(brush = gradientBrush)
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
            
            // PIN authentication with number pad
            if (uiState.pinAvailable) {
                // PIN display (dots)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.Pin,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(modifier = Modifier.width(16.dp))
                    
                    // PIN dots
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        repeat(8) { index ->
                            Box(
                                modifier = Modifier
                                    .size(16.dp)
                                    .then(
                                        if (index < pin.length) {
                                            Modifier
                                        } else {
                                            Modifier
                                        }
                                    ),
                                contentAlignment = Alignment.Center
                            ) {
                                Surface(
                                    shape = CircleShape,
                                    color = if (index < pin.length) {
                                        MaterialTheme.colorScheme.primary
                                    } else {
                                        MaterialTheme.colorScheme.surfaceVariant
                                    },
                                    modifier = Modifier.size(if (index < pin.length) 16.dp else 12.dp)
                                ) {}
                            }
                        }
                    }
                }
                
                if (showError) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = errorMessage,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                
                Spacer(modifier = Modifier.height(32.dp))
                
                // Number pad (3x4 grid) - Glass style
                Column(
                    modifier = Modifier.fillMaxWidth(0.75f), // Make buttons smaller
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Rows 1-3 (numbers 1-9)
                    for (row in 0..2) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)
                        ) {
                            for (col in 1..3) {
                                val number = row * 3 + col
                                Surface(
                                    onClick = {
                                        if (pin.length < 8) {
                                            pin += number
                                            showError = false
                                        }
                                    },
                                    modifier = Modifier
                                        .weight(1f)
                                        .aspectRatio(1f),
                                    shape = CircleShape,
                                    color = Color(0xFF1e293b).copy(alpha = 0.6f), // slate-800 with transparency
                                    tonalElevation = 2.dp,
                                    shadowElevation = 4.dp
                                ) {
                                    Box(
                                        contentAlignment = Alignment.Center,
                                        modifier = Modifier.fillMaxSize()
                                    ) {
                                        Text(
                                            text = number.toString(),
                                            style = MaterialTheme.typography.headlineSmall,
                                            fontWeight = FontWeight.Medium,
                                            color = Color.White.copy(alpha = 0.95f)
                                        )
                                    }
                                }
                            }
                        }
                    }
                    
                    // Row 4 (unlock/empty, 0, backspace)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)
                    ) {
                        // Unlock button (left position, only visible when PIN length >= 4)
                        if (pin.length >= 4) {
                            Surface(
                                onClick = {
                                    val success = viewModel.authenticatePin(pin)
                                    if (!success) {
                                        showError = true
                                        errorMessage = "Falsche PIN"
                                        pin = ""
                                    }
                                },
                                modifier = Modifier
                                    .weight(1f)
                                    .aspectRatio(1f),
                                shape = CircleShape,
                                color = Color(0xFF38bdf8).copy(alpha = 0.85f), // sky-500 for primary action
                                tonalElevation = 4.dp,
                                shadowElevation = 8.dp
                            ) {
                                Box(
                                    contentAlignment = Alignment.Center,
                                    modifier = Modifier.fillMaxSize()
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = "Entsperren",
                                        modifier = Modifier.size(28.dp),
                                        tint = Color.White
                                    )
                                }
                            }
                        } else {
                            // Empty space when unlock button not visible
                            Spacer(modifier = Modifier.weight(1f))
                        }
                        
                        // Number 0
                        Surface(
                            onClick = {
                                if (pin.length < 8) {
                                    pin += "0"
                                    showError = false
                                }
                            },
                            modifier = Modifier
                                .weight(1f)
                                .aspectRatio(1f),
                            shape = CircleShape,
                            color = Color(0xFF1e293b).copy(alpha = 0.6f),
                            tonalElevation = 2.dp,
                            shadowElevation = 4.dp
                        ) {
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier.fillMaxSize()
                            ) {
                                Text(
                                    text = "0",
                                    style = MaterialTheme.typography.headlineSmall,
                                    fontWeight = FontWeight.Medium,
                                    color = Color.White.copy(alpha = 0.95f)
                                )
                            }
                        }
                        
                        // Backspace
                        Surface(
                            onClick = {
                                if (pin.isNotEmpty()) {
                                    pin = pin.dropLast(1)
                                    showError = false
                                }
                            },
                            modifier = Modifier
                                .weight(1f)
                                .aspectRatio(1f),
                            shape = CircleShape,
                            color = if (pin.isNotEmpty()) {
                                Color(0xFF1e293b).copy(alpha = 0.6f)
                            } else {
                                Color(0xFF1e293b).copy(alpha = 0.2f)
                            },
                            tonalElevation = 2.dp,
                            shadowElevation = if (pin.isNotEmpty()) 4.dp else 0.dp
                        ) {
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier.fillMaxSize()
                            ) {
                                Icon(
                                    imageVector = Icons.AutoMirrored.Filled.Backspace,
                                    contentDescription = "Löschen",
                                    modifier = Modifier.size(20.dp),
                                    tint = Color.White.copy(
                                        alpha = if (pin.isNotEmpty()) 0.8f else 0.4f
                                    )
                                )
                            }
                        }
                    }
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
        } // End of inner Box
    } // End of outer Box (gradient background)
}

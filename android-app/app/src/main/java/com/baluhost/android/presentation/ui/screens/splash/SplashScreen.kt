package com.baluhost.android.presentation.ui.screens.splash

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel

/**
 * Splash screen - checks authentication status.
 */
@Composable
fun SplashScreen(
    onNavigateToOnboarding: () -> Unit,
    onNavigateToQrScanner: () -> Unit,
    onNavigateToFiles: () -> Unit,
    viewModel: SplashViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    
    LaunchedEffect(uiState) {
        when (uiState) {
            is SplashState.OnboardingNeeded -> onNavigateToOnboarding()
            is SplashState.Authenticated -> onNavigateToFiles()
            is SplashState.NotAuthenticated -> onNavigateToQrScanner()
            else -> { /* Loading */ }
        }
    }
    
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        when (uiState) {
            is SplashState.Loading -> {
                CircularProgressIndicator()
            }
            else -> {
                Text(
                    text = "BaluHost",
                    style = MaterialTheme.typography.displayLarge,
                    fontSize = 48.sp
                )
            }
        }
    }
}

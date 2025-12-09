package com.baluhost.android.presentation.ui.screens.splash

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Splash Screen.
 * 
 * Checks if user is already authenticated.
 */
@HiltViewModel
class SplashViewModel @Inject constructor(
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<SplashState>(SplashState.Loading)
    val uiState: StateFlow<SplashState> = _uiState.asStateFlow()
    
    init {
        checkAuthentication()
    }
    
    private fun checkAuthentication() {
        viewModelScope.launch {
            delay(1000) // Show splash for minimum 1 second
            
            // Check if onboarding is completed
            val onboardingCompleted = preferencesManager.isOnboardingCompleted().first()
            
            if (!onboardingCompleted) {
                _uiState.value = SplashState.OnboardingNeeded
                return@launch
            }
            
            // Check authentication
            val accessToken = preferencesManager.getAccessToken().first()
            
            _uiState.value = if (accessToken != null) {
                SplashState.Authenticated
            } else {
                SplashState.NotAuthenticated
            }
        }
    }
}

sealed class SplashState {
    object Loading : SplashState()
    object OnboardingNeeded : SplashState()
    object Authenticated : SplashState()
    object NotAuthenticated : SplashState()
}

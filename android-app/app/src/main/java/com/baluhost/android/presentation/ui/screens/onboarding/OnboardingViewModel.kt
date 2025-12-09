package com.baluhost.android.presentation.ui.screens.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.local.datastore.PreferencesManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Onboarding wizard.
 */
@HiltViewModel
class OnboardingViewModel @Inject constructor(
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(OnboardingUiState())
    val uiState: StateFlow<OnboardingUiState> = _uiState.asStateFlow()
    
    fun nextStep() {
        _uiState.update { currentState ->
            val nextPage = (currentState.currentStep + 1).coerceAtMost(OnboardingStep.values().size - 1)
            currentState.copy(currentStep = nextPage)
        }
    }
    
    fun previousStep() {
        _uiState.update { currentState ->
            val prevPage = (currentState.currentStep - 1).coerceAtLeast(0)
            currentState.copy(currentStep = prevPage)
        }
    }
    
    fun goToStep(step: Int) {
        _uiState.update { it.copy(currentStep = step) }
    }
    
    fun skipBiometricSetup() {
        _uiState.update { it.copy(biometricSetupSkipped = true) }
        nextStep()
    }
    
    fun completeOnboarding() {
        viewModelScope.launch {
            preferencesManager.saveOnboardingCompleted(true)
            _uiState.update { it.copy(isCompleted = true) }
        }
    }
}

/**
 * UI state for Onboarding.
 */
data class OnboardingUiState(
    val currentStep: Int = 0,
    val biometricSetupSkipped: Boolean = false,
    val isCompleted: Boolean = false
)

/**
 * Onboarding wizard steps.
 */
enum class OnboardingStep {
    WELCOME,
    QR_SCAN,
    PERMISSIONS,
    BIOMETRIC_SETUP,
    SUCCESS
}

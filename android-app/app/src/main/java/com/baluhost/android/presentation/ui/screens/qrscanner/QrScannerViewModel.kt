package com.baluhost.android.presentation.ui.screens.qrscanner

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.remote.dto.RegistrationQrData
import com.baluhost.android.domain.model.AuthResult
import com.baluhost.android.domain.usecase.auth.RegisterDeviceUseCase
import com.baluhost.android.domain.usecase.vpn.ImportVpnConfigUseCase
import com.baluhost.android.util.Result
import com.google.gson.Gson
import com.google.gson.JsonSyntaxException
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for QR Scanner Screen.
 * 
 * Handles QR code scanning and device registration.
 */
@HiltViewModel
class QrScannerViewModel @Inject constructor(
    private val registerDeviceUseCase: RegisterDeviceUseCase,
    private val importVpnConfigUseCase: ImportVpnConfigUseCase
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<QrScannerState>(QrScannerState.Scanning)
    val uiState: StateFlow<QrScannerState> = _uiState.asStateFlow()
    
    private val gson = Gson()
    
    fun onQrCodeScanned(qrData: String) {
        if (_uiState.value !is QrScannerState.Scanning) return
        
        viewModelScope.launch {
            _uiState.value = QrScannerState.Processing
            
            try {
                // Parse QR code data
                val registrationData = gson.fromJson(qrData, RegistrationQrData::class.java)
                
                // Register device
                val result = registerDeviceUseCase(
                    token = registrationData.token,
                    serverUrl = registrationData.server
                )
                
                when (result) {
                    is Result.Success -> {
                        // Import VPN config if available
                        var vpnImported = false
                        registrationData.vpnConfig?.let { vpnConfig ->
                            viewModelScope.launch {
                                val vpnResult = importVpnConfigUseCase(
                                    configBase64 = vpnConfig,
                                    autoRegister = true
                                )
                                when (vpnResult) {
                                    is Result.Success -> {
                                        android.util.Log.d("QrScanner", "VPN config imported: ${vpnResult.data.serverEndpoint}")
                                        vpnImported = true
                                    }
                                    is Result.Error -> {
                                        android.util.Log.e("QrScanner", "VPN import failed: ${vpnResult.exception.message}")
                                    }
                                    else -> {}
                                }
                            }
                        }
                        
                        _uiState.value = QrScannerState.Success(
                            authResult = result.data,
                            vpnConfigured = vpnImported || registrationData.vpnConfig != null
                        )
                    }
                    is Result.Error -> {
                        _uiState.value = QrScannerState.Error(
                            result.exception.message ?: "Registration failed"
                        )
                    }
                    else -> {
                        _uiState.value = QrScannerState.Error("Unknown error")
                    }
                }
            } catch (e: JsonSyntaxException) {
                _uiState.value = QrScannerState.Error("Invalid QR code format")
            } catch (e: Exception) {
                _uiState.value = QrScannerState.Error(e.message ?: "Unknown error")
            }
        }
    }
    
    fun resetScanner() {
        _uiState.value = QrScannerState.Scanning
    }
}

sealed class QrScannerState {
    object Scanning : QrScannerState()
    object Processing : QrScannerState()
    data class Success(
        val authResult: AuthResult,
        val vpnConfigured: Boolean = false
    ) : QrScannerState()
    data class Error(val message: String) : QrScannerState()
}

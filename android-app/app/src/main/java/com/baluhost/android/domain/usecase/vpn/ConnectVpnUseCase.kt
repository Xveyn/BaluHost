package com.baluhost.android.domain.usecase.vpn

import android.content.Context
import android.content.Intent
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.service.vpn.BaluHostVpnService
import com.baluhost.android.util.Result
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import javax.inject.Inject

/**
 * Use case for connecting to VPN.
 * 
 * Starts the VPN service with stored configuration.
 */
class ConnectVpnUseCase @Inject constructor(
    @ApplicationContext private val context: Context,
    private val preferencesManager: PreferencesManager
) {
    
    suspend operator fun invoke(): Result<Boolean> {
        return try {
            val vpnConfig = preferencesManager.getVpnConfig().first()
                ?: return Result.Error(Exception("No VPN configuration found"))
            
            val intent = Intent(context, BaluHostVpnService::class.java).apply {
                action = BaluHostVpnService.ACTION_CONNECT
                putExtra(BaluHostVpnService.EXTRA_CONFIG, vpnConfig)
            }
            
            context.startForegroundService(intent)
            
            Result.Success(true)
        } catch (e: Exception) {
            Result.Error(Exception("Failed to start VPN: ${e.message}", e))
        }
    }
}

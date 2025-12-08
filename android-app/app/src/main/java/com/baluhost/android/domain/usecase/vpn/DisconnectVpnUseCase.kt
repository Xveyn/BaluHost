package com.baluhost.android.domain.usecase.vpn

import android.content.Context
import android.content.Intent
import com.baluhost.android.service.vpn.BaluHostVpnService
import com.baluhost.android.util.Result
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject

/**
 * Use case for disconnecting from VPN.
 */
class DisconnectVpnUseCase @Inject constructor(
    @ApplicationContext private val context: Context
) {
    
    operator fun invoke(): Result<Boolean> {
        return try {
            val intent = Intent(context, BaluHostVpnService::class.java).apply {
                action = BaluHostVpnService.ACTION_DISCONNECT
            }
            
            context.startService(intent)
            
            Result.Success(true)
        } catch (e: Exception) {
            Result.Error(Exception("Failed to stop VPN: ${e.message}", e))
        }
    }
}

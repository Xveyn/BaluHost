package com.baluhost.android.domain.usecase.vpn

import com.baluhost.android.domain.model.VpnConfig
import com.baluhost.android.domain.repository.VpnRepository
import com.baluhost.android.domain.util.Logger
import com.baluhost.android.util.Result
import javax.inject.Inject

/**
 * Use case for fetching VPN configuration.
 *
 * Fetches config from backend and caches locally.
 * Falls back to cached config if network error occurs.
 */
class FetchVpnConfigUseCase @Inject constructor(
    private val vpnRepository: VpnRepository,
    private val logger: Logger
) {

    suspend operator fun invoke(): Result<VpnConfig> {
        logger.debug(TAG, "Fetching VPN config")

        return vpnRepository.fetchVpnConfig()
    }

    companion object {
        private const val TAG = "FetchVpnConfigUseCase"
    }
}

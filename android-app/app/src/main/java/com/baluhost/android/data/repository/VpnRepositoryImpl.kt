package com.baluhost.android.data.repository

import com.baluhost.android.data.remote.api.VpnApi
import com.baluhost.android.domain.repository.VpnRepository
import javax.inject.Inject

/**
 * Implementation of VpnRepository.
 * 
 * Handles VPN operations.
 */
class VpnRepositoryImpl @Inject constructor(
    private val vpnApi: VpnApi
) : VpnRepository {
    // TODO: Implement VPN methods
}

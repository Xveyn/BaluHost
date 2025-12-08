package com.baluhost.android.data.repository

import com.baluhost.android.data.remote.api.AuthApi
import com.baluhost.android.domain.repository.AuthRepository
import javax.inject.Inject

/**
 * Implementation of AuthRepository.
 * 
 * Handles authentication operations.
 */
class AuthRepositoryImpl @Inject constructor(
    private val authApi: AuthApi
) : AuthRepository {
    // TODO: Implement auth methods
}

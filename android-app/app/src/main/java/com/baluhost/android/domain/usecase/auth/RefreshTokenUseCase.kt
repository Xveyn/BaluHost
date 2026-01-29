package com.baluhost.android.domain.usecase.auth

import com.baluhost.android.domain.repository.AuthRepository
import com.baluhost.android.util.Result
import javax.inject.Inject

/**
 * Use case for refreshing access token using refresh token.
 *
 * Returns new access token on success.
 * Delegates to AuthRepository for token refresh logic.
 */
class RefreshTokenUseCase @Inject constructor(
    private val authRepository: AuthRepository
) {

    suspend operator fun invoke(): Result<String> {
        return authRepository.refreshToken()
    }
}

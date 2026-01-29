package com.baluhost.android.domain.usecase.files

import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.domain.repository.FilesRepository
import com.baluhost.android.domain.util.Logger
import com.baluhost.android.util.Result
import kotlinx.coroutines.flow.first
import javax.inject.Inject

/**
 * Use case for getting list of files in a directory.
 *
 * Uses cache-first strategy: returns cached data if available,
 * then refreshes from network in background.
 */
class GetFilesUseCase @Inject constructor(
    private val filesRepository: FilesRepository,
    private val logger: Logger
) {

    suspend operator fun invoke(
        path: String = "",
        forceRefresh: Boolean = false
    ): Result<List<FileItem>> {
        return try {
            // Get cached data first (will auto-refresh if stale)
            // Returns empty list if no cache and network fails - that's OK
            val files = filesRepository.getFiles(path, forceRefresh).first()
            Result.Success(files)
        } catch (e: Exception) {
            // Even on error, return success with empty list to avoid navigation to QR screen
            // The UI will show "Server offline" banner via ServerConnectivityChecker
            logger.warn(TAG, "Failed to load files, returning empty list: ${e.message}")
            Result.Success(emptyList())
        }
    }

    companion object {
        private const val TAG = "GetFilesUseCase"
    }
}

package com.baluhost.android.data.repository

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.domain.repository.FilesRepository
import javax.inject.Inject

/**
 * Implementation of FilesRepository.
 * 
 * Handles file operations.
 */
class FilesRepositoryImpl @Inject constructor(
    private val filesApi: FilesApi
) : FilesRepository {
    // TODO: Implement file methods
}

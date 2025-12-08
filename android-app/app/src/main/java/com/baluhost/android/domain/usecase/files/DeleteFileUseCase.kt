package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.util.Result
import javax.inject.Inject

/**
 * Use case for deleting a file or folder.
 */
class DeleteFileUseCase @Inject constructor(
    private val filesApi: FilesApi
) {
    
    suspend operator fun invoke(path: String): Result<Boolean> {
        return try {
            filesApi.deleteFile(path)
            Result.Success(true)
        } catch (e: Exception) {
            Result.Error(Exception("Delete failed: ${e.message}", e))
        }
    }
}

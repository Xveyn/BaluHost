package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.data.remote.dto.MoveFileRequest
import com.baluhost.android.util.Result
import javax.inject.Inject

/**
 * Use case for moving a file to a different directory.
 */
class MoveFileUseCase @Inject constructor(
    private val filesApi: FilesApi
) {
    
    suspend operator fun invoke(
        sourcePath: String,
        destinationPath: String
    ): Result<Unit> {
        return try {
            val response = filesApi.moveFile(
                MoveFileRequest(
                    sourcePath = sourcePath,
                    destinationPath = destinationPath
                )
            )
            Result.Success(Unit)
        } catch (e: Exception) {
            Result.Error(e)
        }
    }
}

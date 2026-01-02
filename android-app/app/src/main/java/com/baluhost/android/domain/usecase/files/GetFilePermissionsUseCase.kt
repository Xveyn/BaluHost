package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.data.remote.dto.FilePermissionsDto
import com.baluhost.android.util.Result
import javax.inject.Inject

class GetFilePermissionsUseCase @Inject constructor(
    private val filesApi: FilesApi
) {
    suspend operator fun invoke(path: String): Result<FilePermissionsDto> {
        return try {
            val dto = filesApi.getFilePermissions(path)
            Result.Success(dto)
        } catch (e: Exception) {
            Result.Error(Exception("Failed to load permissions: ${e.message}", e))
        }
    }
}

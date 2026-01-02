package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.data.remote.dto.FilePermissionsDto
import com.baluhost.android.data.remote.dto.FilePermissionsRequestDto
import com.baluhost.android.util.Result
import javax.inject.Inject

class UpdateFilePermissionsUseCase @Inject constructor(
    private val filesApi: FilesApi
) {
    suspend operator fun invoke(request: FilePermissionsRequestDto): Result<FilePermissionsDto> {
        return try {
            val dto = filesApi.updateFilePermissions(request)
            Result.Success(dto)
        } catch (e: Exception) {
            Result.Error(Exception("Failed to update permissions: ${e.message}", e))
        }
    }
}

package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.util.Result
import java.time.Instant
import javax.inject.Inject

/**
 * Use case for getting list of files in a directory.
 */
class GetFilesUseCase @Inject constructor(
    private val filesApi: FilesApi
) {
    
    suspend operator fun invoke(path: String = "/"): Result<List<FileItem>> {
        return try {
            val response = filesApi.listFiles(path)
            
            val files = response.files.map { dto ->
                FileItem(
                    name = dto.name,
                    path = dto.path,
                    size = dto.size,
                    isDirectory = dto.isDirectory,
                    modifiedAt = Instant.parse(dto.modifiedAt),
                    owner = dto.owner,
                    permissions = dto.permissions,
                    mimeType = dto.mimeType
                )
            }
            
            Result.Success(files)
        } catch (e: Exception) {
            Result.Error(Exception("Failed to load files: ${e.message}", e))
        }
    }
}

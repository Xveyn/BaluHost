package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.util.Result
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.time.Instant
import javax.inject.Inject

/**
 * Use case for uploading a file.
 */
class UploadFileUseCase @Inject constructor(
    private val filesApi: FilesApi
) {
    
    suspend operator fun invoke(
        file: File,
        destinationPath: String
    ): Result<FileItem> {
        return try {
            val requestBody = file.asRequestBody("application/octet-stream".toMediaTypeOrNull())
            val multipartBody = MultipartBody.Part.createFormData(
                "file",
                file.name,
                requestBody
            )
            
            val response = filesApi.uploadFile(multipartBody, destinationPath)
            
            Result.Success(
                FileItem(
                    name = response.file.name,
                    path = response.file.path,
                    size = response.file.size,
                    isDirectory = response.file.isDirectory,
                    modifiedAt = Instant.parse(response.file.modifiedAt),
                    owner = response.file.owner,
                    permissions = response.file.permissions,
                    mimeType = response.file.mimeType
                )
            )
        } catch (e: Exception) {
            Result.Error(Exception("Upload failed: ${e.message}", e))
        }
    }
}

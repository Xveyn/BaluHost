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
                "files",  // Backend expects 'files' (plural)
                file.name,
                requestBody
            )
            
            // Path must be sent as Form data, not query parameter
            val pathBody = okhttp3.RequestBody.create(
                "text/plain".toMediaTypeOrNull(),
                destinationPath
            )
            
            val response = filesApi.uploadFile(multipartBody, pathBody)
            
            // Backend returns { message, uploaded, upload_ids } - no file details
            // We'll return success and let the caller refresh the file list
            Result.Success(
                FileItem(
                    name = file.name,
                    path = "$destinationPath/${file.name}",
                    size = file.length(),
                    isDirectory = false,
                    modifiedAt = Instant.now(),
                    owner = null,
                    permissions = null,
                    mimeType = null
                )
            )
        } catch (e: Exception) {
            Result.Error(Exception("Upload failed: ${e.message}", e))
        }
    }
}

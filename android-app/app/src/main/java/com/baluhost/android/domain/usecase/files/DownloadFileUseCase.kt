package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.util.Result
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject

/**
 * Use case for downloading a file.
 */
class DownloadFileUseCase @Inject constructor(
    private val filesApi: FilesApi
) {
    
    suspend operator fun invoke(
        path: String,
        destinationFile: File
    ): Result<File> {
        return try {
            val responseBody = filesApi.downloadFile(path)
            
            withContext(Dispatchers.IO) {
                destinationFile.outputStream().use { output ->
                    responseBody.byteStream().use { input ->
                        input.copyTo(output)
                    }
                }
            }
            
            Result.Success(destinationFile)
        } catch (e: Exception) {
            Result.Error(Exception("Download failed: ${e.message}", e))
        }
    }
}

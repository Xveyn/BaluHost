package com.baluhost.android.data.remote.api

import com.baluhost.android.data.remote.dto.CreateFolderRequest
import com.baluhost.android.data.remote.dto.CreateFolderResponse
import com.baluhost.android.data.remote.dto.DeleteFileResponse
import com.baluhost.android.data.remote.dto.FileListResponse
import com.baluhost.android.data.remote.dto.FileMetadataResponse
import com.baluhost.android.data.remote.dto.MoveFileRequest
import com.baluhost.android.data.remote.dto.MoveFileResponse
import com.baluhost.android.data.remote.dto.RenameFileRequest
import com.baluhost.android.data.remote.dto.RenameFileResponse
import com.baluhost.android.data.remote.dto.UploadFileResponse
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

/**
 * File management API endpoints.
 */
interface FilesApi {
    
    @GET("files/list")
    suspend fun listFiles(
        @Query("path") path: String = "/"
    ): FileListResponse
    
    @Multipart
    @POST("files/upload")
    suspend fun uploadFile(
        @Part files: MultipartBody.Part,
        @Part("path") path: okhttp3.RequestBody
    ): UploadFileResponse
    
    @Streaming
    @GET("files/download")
    suspend fun downloadFile(
        @Query("path") path: String
    ): ResponseBody
    
    @DELETE("files/{path}")
    suspend fun deleteFile(
        @Path("path", encoded = true) path: String
    ): DeleteFileResponse
    
    @POST("files/folder")
    suspend fun createFolder(
        @Body request: CreateFolderRequest
    ): CreateFolderResponse
    
    @PUT("files/move")
    suspend fun moveFile(
        @Body request: MoveFileRequest
    ): MoveFileResponse
    
    @PUT("files/rename")
    suspend fun renameFile(
        @Body request: RenameFileRequest
    ): RenameFileResponse
    
    @GET("files/metadata")
    suspend fun getFileMetadata(
        @Query("path") path: String
    ): FileMetadataResponse
}

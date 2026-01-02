package com.baluhost.android.domain.usecase.files

import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.data.remote.dto.DeleteFileResponse
import com.baluhost.android.util.Result
import io.mockk.*
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*

class DeleteFileUseCaseTest {
    
    private lateinit var filesApi: FilesApi
    private lateinit var deleteFileUseCase: DeleteFileUseCase
    
    @Before
    fun setup() {
        filesApi = mockk()
        deleteFileUseCase = DeleteFileUseCase(filesApi)
    }
    
    @After
    fun teardown() {
        clearAllMocks()
    }
    
    @Test
    fun `invoke should return success when file deletion succeeds`() = runTest {
        // Given
        val filePath = "documents/file.txt"
        
        coEvery {
            filesApi.deleteFile(filePath)
        } returns DeleteFileResponse(message = "deleted", path = filePath)
        
        // When
        val result = deleteFileUseCase(filePath)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        assertTrue(successResult.data)
        
        coVerify(exactly = 1) {
            filesApi.deleteFile(filePath)
        }
    }
    
    @Test
    fun `invoke should return success when folder deletion succeeds`() = runTest {
        // Given
        val folderPath = "documents/folder"
        
        coEvery {
            filesApi.deleteFile(folderPath)
        } returns DeleteFileResponse(message = "deleted", path = folderPath)
        
        // When
        val result = deleteFileUseCase(folderPath)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        assertTrue(successResult.data)
    }
    
    @Test
    fun `invoke should return error when file not found`() = runTest {
        // Given
        val filePath = "documents/nonexistent.txt"
        val errorMessage = "File not found"
        
        coEvery {
            filesApi.deleteFile(filePath)
        } throws Exception(errorMessage)
        
        // When
        val result = deleteFileUseCase(filePath)
        
        // Then
        assertTrue(result is Result.Error)
        val errorResult = result as Result.Error
        assertEquals(errorMessage, errorResult.exception.message)
    }
    
    @Test
    fun `invoke should return error when user lacks permissions`() = runTest {
        // Given
        val filePath = "documents/protected.txt"
        val errorMessage = "Permission denied"
        
        coEvery {
            filesApi.deleteFile(filePath)
        } throws Exception(errorMessage)
        
        // When
        val result = deleteFileUseCase(filePath)
        
        // Then
        assertTrue(result is Result.Error)
        val errorResult = result as Result.Error
        assertTrue(errorResult.exception.message?.contains("Permission denied") == true)
    }
    
    @Test
    fun `invoke should handle network errors`() = runTest {
        // Given
        val filePath = "documents/file.txt"
        
        coEvery {
            filesApi.deleteFile(filePath)
        } throws Exception("Network error")
        
        // When
        val result = deleteFileUseCase(filePath)
        
        // Then
        assertTrue(result is Result.Error)
    }
}

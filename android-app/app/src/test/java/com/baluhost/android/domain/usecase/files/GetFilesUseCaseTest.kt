package com.baluhost.android.domain.usecase.files

import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.domain.repository.FilesRepository
import com.baluhost.android.util.Result
import io.mockk.*
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*

class GetFilesUseCaseTest {
    
    private lateinit var filesRepository: FilesRepository
    private lateinit var getFilesUseCase: GetFilesUseCase
    
    @Before
    fun setup() {
        filesRepository = mockk()
        getFilesUseCase = GetFilesUseCase(filesRepository)
    }
    
    @After
    fun teardown() {
        clearAllMocks()
    }
    
    @Test
    fun `invoke should return file list when repository call succeeds`() = runTest {
        // Given
        val path = "documents"
        val expectedFiles = listOf(
            FileItem(
                name = "file1.txt",
                path = "documents/file1.txt",
                size = 1024,
                isDirectory = false,
                modifiedAt = System.currentTimeMillis() / 1000,
                owner = "user1"
            ),
            FileItem(
                name = "folder1",
                path = "documents/folder1",
                size = 0,
                isDirectory = true,
                modifiedAt = System.currentTimeMillis() / 1000,
                owner = "user1"
            )
        )
        
        coEvery { 
            filesRepository.listFiles(path)
        } returns Result.Success(expectedFiles)
        
        // When
        val result = getFilesUseCase(path)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        assertEquals(2, successResult.data.size)
        assertEquals("file1.txt", successResult.data[0].name)
        assertEquals("folder1", successResult.data[1].name)
        assertTrue(successResult.data[1].isDirectory)
        
        coVerify(exactly = 1) {
            filesRepository.listFiles(path)
        }
    }
    
    @Test
    fun `invoke should return empty list when directory is empty`() = runTest {
        // Given
        val path = "empty_folder"
        
        coEvery { 
            filesRepository.listFiles(path)
        } returns Result.Success(emptyList())
        
        // When
        val result = getFilesUseCase(path)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        assertTrue(successResult.data.isEmpty())
    }
    
    @Test
    fun `invoke should return error when repository call fails`() = runTest {
        // Given
        val path = "documents"
        val errorMessage = "Failed to list files"
        
        coEvery { 
            filesRepository.listFiles(path)
        } returns Result.Error(Exception(errorMessage))
        
        // When
        val result = getFilesUseCase(path)
        
        // Then
        assertTrue(result is Result.Error)
        val errorResult = result as Result.Error
        assertEquals(errorMessage, errorResult.exception.message)
    }
    
    @Test
    fun `invoke should handle root path correctly`() = runTest {
        // Given
        val path = ""
        val rootFiles = listOf(
            FileItem(
                name = "Documents",
                path = "Documents",
                size = 0,
                isDirectory = true,
                modifiedAt = System.currentTimeMillis() / 1000,
                owner = "user1"
            ),
            FileItem(
                name = "Pictures",
                path = "Pictures",
                size = 0,
                isDirectory = true,
                modifiedAt = System.currentTimeMillis() / 1000,
                owner = "user1"
            )
        )
        
        coEvery { 
            filesRepository.listFiles(path)
        } returns Result.Success(rootFiles)
        
        // When
        val result = getFilesUseCase(path)
        
        // Then
        assertTrue(result is Result.Success)
        val successResult = result as Result.Success
        assertEquals(2, successResult.data.size)
        assertTrue(successResult.data.all { it.isDirectory })
    }
}

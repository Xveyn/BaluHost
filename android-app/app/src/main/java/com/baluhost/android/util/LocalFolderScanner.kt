package com.baluhost.android.util

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.documentfile.provider.DocumentFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Utility for scanning local folders using Storage Access Framework.
 * Used for folder synchronization to detect files and calculate sizes.
 */
class LocalFolderScanner(private val context: Context) {
    
    /**
     * Scan result containing folder statistics.
     */
    data class ScanResult(
        val totalFiles: Int,
        val totalSize: Long,
        val fileList: List<FileInfo>,
        val errors: List<String>
    )
    
    /**
     * File information from scan.
     */
    data class FileInfo(
        val uri: Uri,
        val name: String,
        val size: Long,
        val lastModified: Long,
        val mimeType: String?,
        val isDirectory: Boolean,
        val relativePath: String,
        val hash: String = ""  // SHA256 hash for change detection
    )
    
    /**
     * Scan a folder URI and return statistics.
     * 
     * @param folderUri The content URI from DocumentsContract.EXTRA_INITIAL_URI
     * @param recursive Whether to scan subdirectories
     * @param excludePatterns List of patterns to exclude (e.g., ".tmp", ".cache")
     * @return ScanResult with file count, size, and file list
     */
    suspend fun scanFolder(
        folderUri: Uri,
        recursive: Boolean = true,
        excludePatterns: List<String> = emptyList()
    ): ScanResult = withContext(Dispatchers.IO) {
        val documentFile = DocumentFile.fromTreeUri(context, folderUri)
            ?: return@withContext ScanResult(0, 0, emptyList(), listOf("Invalid folder URI"))
        
        if (!documentFile.exists() || !documentFile.isDirectory) {
            return@withContext ScanResult(
                0, 0, emptyList(),
                listOf("Folder does not exist or is not a directory")
            )
        }
        
        val files = mutableListOf<FileInfo>()
        val errors = mutableListOf<String>()
        var totalSize = 0L
        
        scanDirectoryRecursive(
            documentFile = documentFile,
            basePath = "",
            files = files,
            errors = errors,
            totalSize = { totalSize += it },
            recursive = recursive,
            excludePatterns = excludePatterns
        )
        
        ScanResult(
            totalFiles = files.size,
            totalSize = totalSize,
            fileList = files,
            errors = errors
        )
    }
    
    /**
     * Recursively scan a directory.
     */
    private fun scanDirectoryRecursive(
        documentFile: DocumentFile,
        basePath: String,
        files: MutableList<FileInfo>,
        errors: MutableList<String>,
        totalSize: (Long) -> Unit,
        recursive: Boolean,
        excludePatterns: List<String>
    ) {
        try {
            val children = documentFile.listFiles()
            
            for (child in children) {
                val childName = child.name ?: continue
                
                // Skip system/hidden files
                if (childName.startsWith(".")) continue
                
                // Check exclude patterns
                if (excludePatterns.any { pattern ->
                    childName.contains(pattern, ignoreCase = true)
                }) continue
                
                val relativePath = if (basePath.isEmpty()) childName else "$basePath/$childName"
                
                if (child.isDirectory) {
                    if (recursive) {
                        scanDirectoryRecursive(
                            documentFile = child,
                            basePath = relativePath,
                            files = files,
                            errors = errors,
                            totalSize = totalSize,
                            recursive = true,
                            excludePatterns = excludePatterns
                        )
                    }
                } else if (child.isFile) {
                    val size = child.length()
                    totalSize(size)
                    
                    files.add(
                        FileInfo(
                            uri = child.uri,
                            name = childName,
                            size = size,
                            lastModified = child.lastModified(),
                            mimeType = child.type,
                            isDirectory = false,
                            relativePath = relativePath
                        )
                    )
                }
            }
        } catch (e: Exception) {
            errors.add("Error scanning ${documentFile.name}: ${e.message}")
        }
    }
    
    /**
     * Calculate SHA256 hash of a file for change detection.
     */
    suspend fun calculateFileHash(fileUri: Uri): String? = withContext(Dispatchers.IO) {
        try {
            context.contentResolver.openInputStream(fileUri)?.use { input ->
                val digest = java.security.MessageDigest.getInstance("SHA-256")
                val buffer = ByteArray(8192)
                var bytesRead: Int
                
                while (input.read(buffer).also { bytesRead = it } != -1) {
                    digest.update(buffer, 0, bytesRead)
                }
                
                digest.digest().joinToString("") { "%02x".format(it) }
            }
        } catch (e: Exception) {
            null
        }
    }
    
    /**
     * Calculate SHA256 hash of a file (from File object).
     */
    fun calculateFileHash(file: java.io.File): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(8192)
            var bytesRead: Int
            
            while (input.read(buffer).also { bytesRead = it } != -1) {
                digest.update(buffer, 0, bytesRead)
            }
        }
        
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    
    /**
     * Check if folder URI is still accessible.
     */
    fun isFolderAccessible(folderUri: Uri): Boolean {
        return try {
            val documentFile = DocumentFile.fromTreeUri(context, folderUri)
            documentFile?.exists() == true && documentFile.isDirectory
        } catch (e: Exception) {
            false
        }
    }
    
    /**
     * Get folder display name.
     */
    fun getFolderDisplayName(folderUri: Uri): String? {
        return try {
            val documentFile = DocumentFile.fromTreeUri(context, folderUri)
            documentFile?.name
        } catch (e: Exception) {
            null
        }
    }
    
    /**
     * Format bytes to human-readable string.
     */
    fun formatBytes(bytes: Long): String {
        val units = arrayOf("B", "KB", "MB", "GB", "TB")
        var size = bytes.toDouble()
        var unitIndex = 0
        
        while (size >= 1024 && unitIndex < units.size - 1) {
            size /= 1024
            unitIndex++
        }
        
        return "%.1f %s".format(size, units[unitIndex])
    }
}

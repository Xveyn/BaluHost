package com.baluhost.android.util

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat

/**
 * Helper class for managing Android runtime permissions.
 * Handles storage permissions for different Android versions.
 */
object PermissionHelper {
    
    /**
     * Permissions needed for folder sync on different Android versions.
     */
    fun getStoragePermissions(): Array<String> {
        return when {
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU -> {
                // Android 13+ uses granular media permissions
                arrayOf(
                    android.Manifest.permission.READ_MEDIA_IMAGES,
                    android.Manifest.permission.READ_MEDIA_VIDEO
                )
            }
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.R -> {
                // Android 11-12 uses scoped storage
                arrayOf(
                    android.Manifest.permission.READ_EXTERNAL_STORAGE,
                    android.Manifest.permission.MANAGE_EXTERNAL_STORAGE
                )
            }
            else -> {
                // Android 10 and below
                arrayOf(
                    android.Manifest.permission.READ_EXTERNAL_STORAGE,
                    android.Manifest.permission.WRITE_EXTERNAL_STORAGE
                )
            }
        }
    }
    
    /**
     * Check if all required storage permissions are granted.
     */
    fun hasStoragePermissions(context: Context): Boolean {
        return getStoragePermissions().all { permission ->
            ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
        }
    }
    
    /**
     * Get user-friendly permission descriptions.
     */
    fun getPermissionDescription(permission: String): String {
        return when (permission) {
            android.Manifest.permission.READ_EXTERNAL_STORAGE,
            android.Manifest.permission.READ_MEDIA_IMAGES,
            android.Manifest.permission.READ_MEDIA_VIDEO -> 
                "Zugriff auf Dateien und Ordner zum Synchronisieren"
            android.Manifest.permission.WRITE_EXTERNAL_STORAGE -> 
                "Schreibzugriff zum Herunterladen synchronisierter Dateien"
            android.Manifest.permission.MANAGE_EXTERNAL_STORAGE -> 
                "Vollständiger Dateizugriff für umfassende Synchronisation"
            else -> "Erforderliche Berechtigung"
        }
    }
    
    /**
     * Get a message explaining why permissions are needed.
     */
    fun getPermissionRationale(): String {
        return """
            BaluHost benötigt Berechtigungen zum Zugriff auf den Speicher des Smartphones, 
            um Dateien und Ordner zu synchronisieren.
            
            • Dateien lesen und hochladen zum NAS
            • Synchronisierte Dateien herunterladen
            • Fortschritt in Echtzeit verfolgenhängen
        """.trimIndent()
    }
}

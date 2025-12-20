package com.baluhost.android.util

object Constants {
    // Network
    const val CONNECT_TIMEOUT = 10L // seconds - faster offline detection
    const val READ_TIMEOUT = 10L // seconds - faster offline detection
    const val WRITE_TIMEOUT = 30L // seconds - longer for uploads
    
    // Authentication
    const val TOKEN_EXPIRY_BUFFER = 60 // seconds before expiry to refresh
    const val MAX_REFRESH_RETRIES = 3
    
    // File Operations
    const val CHUNK_SIZE = 8192 // bytes for file upload/download
    const val MAX_FILE_SIZE = 5L * 1024 * 1024 * 1024 // 5 GB
    
    // VPN
    const val VPN_MTU = 1280
    const val VPN_NOTIFICATION_ID = 1001
    const val VPN_NOTIFICATION_CHANNEL = "vpn_service_channel"
    
    // Camera Backup
    const val BACKUP_NOTIFICATION_ID = 1002
    const val BACKUP_NOTIFICATION_CHANNEL = "backup_service_channel"
    const val BACKUP_WORK_NAME = "camera_backup"
    const val BACKUP_INTERVAL_HOURS = 6L
    
    // Database
    const val DATABASE_NAME = "baluhost.db"
    const val DATABASE_VERSION = 1
    
    // Preferences Keys
    object PrefsKeys {
        const val ACCESS_TOKEN = "access_token"
        const val REFRESH_TOKEN = "refresh_token"
        const val SERVER_URL = "server_url"
        const val USER_ID = "user_id"
        const val USERNAME = "username"
        const val CAMERA_BACKUP_ENABLED = "camera_backup_enabled"
        const val WIFI_ONLY = "wifi_only"
        const val LAST_BACKUP_TIME = "last_backup_time"
        const val VPN_CONFIG = "vpn_config"
    }
    
    // Intent Actions
    object Actions {
        const val VPN_CONNECT = "com.baluhost.android.vpn.CONNECT"
        const val VPN_DISCONNECT = "com.baluhost.android.vpn.DISCONNECT"
    }
    
    // API Endpoints (relative to BASE_URL)
    object Endpoints {
        const val AUTH_LOGIN = "auth/login"
        const val AUTH_REFRESH = "auth/refresh"
        const val MOBILE_REGISTER = "mobile/register"
        const val MOBILE_TOKEN_GENERATE = "mobile/token/generate"
        const val FILES_LIST = "files/list"
        const val FILES_UPLOAD = "files/upload"
        const val FILES_DOWNLOAD = "files/download"
        const val FILES_DELETE = "files/delete"
        const val VPN_GENERATE_CONFIG = "vpn/generate-config"
        const val VPN_CLIENTS = "vpn/clients"
    }
}

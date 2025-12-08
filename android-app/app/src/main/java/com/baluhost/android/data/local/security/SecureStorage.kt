package com.baluhost.android.data.local.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Secure storage for sensitive data using EncryptedSharedPreferences.
 * 
 * Uses Android Keystore for encryption.
 * Store sensitive data like tokens, keys here.
 */
@Singleton
class SecureStorage @Inject constructor(
    context: Context
) {
    
    private val masterKey = MasterKey.Builder(context)
        .setKeyGenParameterSpec(
            KeyGenParameterSpec.Builder(
                MasterKey.DEFAULT_MASTER_KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        .build()
    
    private val encryptedPrefs = EncryptedSharedPreferences.create(
        context,
        PREFS_NAME,
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    
    // Access Token
    fun saveAccessToken(token: String) {
        encryptedPrefs.edit().putString(KEY_ACCESS_TOKEN, token).apply()
    }
    
    fun getAccessToken(): String? {
        return encryptedPrefs.getString(KEY_ACCESS_TOKEN, null)
    }
    
    // Refresh Token
    fun saveRefreshToken(token: String) {
        encryptedPrefs.edit().putString(KEY_REFRESH_TOKEN, token).apply()
    }
    
    fun getRefreshToken(): String? {
        return encryptedPrefs.getString(KEY_REFRESH_TOKEN, null)
    }
    
    // VPN Private Key
    fun saveVpnPrivateKey(key: String) {
        encryptedPrefs.edit().putString(KEY_VPN_PRIVATE_KEY, key).apply()
    }
    
    fun getVpnPrivateKey(): String? {
        return encryptedPrefs.getString(KEY_VPN_PRIVATE_KEY, null)
    }
    
    // Clear all secure data
    fun clearAll() {
        encryptedPrefs.edit().clear().apply()
    }
    
    companion object {
        private const val PREFS_NAME = "baluhost_secure_prefs"
        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_VPN_PRIVATE_KEY = "vpn_private_key"
    }
}

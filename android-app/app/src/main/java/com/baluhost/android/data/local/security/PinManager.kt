package com.baluhost.android.data.local.security

import java.security.MessageDigest
import java.security.SecureRandom
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manager for PIN-based authentication (fallback when biometric unavailable).
 * 
 * Implements secure PIN storage using SHA-256 hashing with salt.
 * 
 * Best Practices:
 * - Never stores PIN in plain text
 * - Uses cryptographically secure random salt
 * - SHA-256 hashing for PIN storage
 * - Salt is unique per device
 * - Constant-time comparison to prevent timing attacks
 */
@Singleton
class PinManager @Inject constructor(
    private val securePreferences: SecurePreferencesManager
) {
    
    companion object {
        private const val TAG = "PinManager"
        private const val SALT_LENGTH = 32 // 32 bytes = 256 bits
        private const val MIN_PIN_LENGTH = 4
        private const val MAX_PIN_LENGTH = 8
    }
    
    /**
     * Validate PIN length and format.
     * 
     * @param pin PIN to validate
     * @return true if valid, false otherwise
     */
    fun isValidPin(pin: String): Boolean {
        return pin.length in MIN_PIN_LENGTH..MAX_PIN_LENGTH && pin.all { it.isDigit() }
    }
    
    /**
     * Set up a new PIN.
     * Generates random salt, hashes PIN with salt, and stores securely.
     * 
     * @param pin Plain-text PIN (4-8 digits)
     * @return true if setup successful, false if PIN invalid
     */
    fun setupPin(pin: String): Boolean {
        if (!isValidPin(pin)) {
            android.util.Log.w(TAG, "Invalid PIN format: length must be $MIN_PIN_LENGTH-$MAX_PIN_LENGTH digits")
            return false
        }
        
        try {
            // Generate cryptographically secure random salt
            val salt = generateSalt()
            
            // Hash PIN with salt
            val hash = hashPinWithSalt(pin, salt)
            
            // Store hash and salt securely
            securePreferences.savePinHash(hash, salt)
            
            android.util.Log.d(TAG, "PIN setup successful")
            return true
        } catch (e: Exception) {
            android.util.Log.e(TAG, "Failed to setup PIN", e)
            return false
        }
    }
    
    /**
     * Verify provided PIN against stored hash.
     * 
     * @param pin Plain-text PIN to verify
     * @return true if PIN matches, false otherwise
     */
    fun verifyPin(pin: String): Boolean {
        if (!isValidPin(pin)) {
            return false
        }
        
        val storedHash = securePreferences.getPinHash()
        val salt = securePreferences.getPinSalt()
        
        if (storedHash == null || salt == null) {
            android.util.Log.w(TAG, "No PIN configured")
            return false
        }
        
        try {
            // Hash provided PIN with stored salt
            val computedHash = hashPinWithSalt(pin, salt)
            
            // Constant-time comparison to prevent timing attacks
            return constantTimeEquals(storedHash, computedHash)
        } catch (e: Exception) {
            android.util.Log.e(TAG, "Failed to verify PIN", e)
            return false
        }
    }
    
    /**
     * Check if PIN is configured.
     */
    fun isPinConfigured(): Boolean {
        return securePreferences.hasPinConfigured()
    }
    
    /**
     * Remove PIN configuration.
     */
    fun removePin() {
        securePreferences.clearPin()
        android.util.Log.d(TAG, "PIN removed")
    }
    
    /**
     * Change existing PIN.
     * 
     * @param oldPin Current PIN for verification
     * @param newPin New PIN to set
     * @return true if change successful, false if old PIN incorrect or new PIN invalid
     */
    fun changePin(oldPin: String, newPin: String): Boolean {
        // Verify old PIN first
        if (!verifyPin(oldPin)) {
            android.util.Log.w(TAG, "Old PIN verification failed")
            return false
        }
        
        // Setup new PIN
        return setupPin(newPin)
    }
    
    /**
     * Generate cryptographically secure random salt.
     */
    private fun generateSalt(): String {
        val random = SecureRandom()
        val salt = ByteArray(SALT_LENGTH)
        random.nextBytes(salt)
        return bytesToHex(salt)
    }
    
    /**
     * Hash PIN with salt using SHA-256.
     * 
     * @param pin Plain-text PIN
     * @param salt Hex-encoded salt
     * @return Hex-encoded hash
     */
    private fun hashPinWithSalt(pin: String, salt: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        
        // Combine PIN and salt
        val combined = pin + salt
        
        // Hash the combined value
        val hashBytes = digest.digest(combined.toByteArray(Charsets.UTF_8))
        
        return bytesToHex(hashBytes)
    }
    
    /**
     * Convert byte array to hexadecimal string.
     */
    private fun bytesToHex(bytes: ByteArray): String {
        return bytes.joinToString("") { "%02x".format(it) }
    }
    
    /**
     * Constant-time string comparison to prevent timing attacks.
     * 
     * @param a First string
     * @param b Second string
     * @return true if strings are equal, false otherwise
     */
    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) {
            return false
        }
        
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].code xor b[i].code)
        }
        
        return result == 0
    }
}

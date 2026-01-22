#pragma once

#include <string>

namespace baludesk {

/**
 * CredentialStore - Secure credential storage using OS-native keychains
 *
 * Platform-specific implementations:
 * - Windows: Windows Credential Manager (wincred.h)
 * - macOS: Keychain Services (Security/Security.h)
 * - Linux: libsecret (GNOME Keyring / KWallet)
 *
 * All credentials are encrypted by the operating system and stored
 * securely. No plaintext credentials are ever written to disk.
 *
 * Usage:
 *   // Save token
 *   CredentialStore::saveToken("username", "jwt_token_here");
 *
 *   // Load token
 *   std::string token = CredentialStore::loadToken("username");
 *
 *   // Delete token
 *   CredentialStore::deleteToken("username");
 */
class CredentialStore {
public:
    /**
     * Save authentication token for a user
     *
     * @param username The username to associate with this token
     * @param token The JWT token to store securely
     * @return true if saved successfully, false otherwise
     */
    static bool saveToken(const std::string& username, const std::string& token);

    /**
     * Load authentication token for a user
     *
     * @param username The username whose token to retrieve
     * @return The JWT token, or empty string if not found or error occurred
     */
    static std::string loadToken(const std::string& username);

    /**
     * Delete stored token for a user
     *
     * @param username The username whose token to delete
     * @return true if deleted successfully, false otherwise
     */
    static bool deleteToken(const std::string& username);

    /**
     * Check if a token exists for a user
     *
     * @param username The username to check
     * @return true if token exists, false otherwise
     */
    static bool hasToken(const std::string& username);

private:
    // Service/Target name for credential storage
    static constexpr const char* SERVICE_NAME = "BaluDesk";

#ifdef _WIN32
    // Windows-specific implementation
    static bool saveTokenWindows(const std::string& username, const std::string& token);
    static std::string loadTokenWindows(const std::string& username);
    static bool deleteTokenWindows(const std::string& username);
    static bool hasTokenWindows(const std::string& username);
#elif __APPLE__
    // macOS-specific implementation
    static bool saveTokenMac(const std::string& username, const std::string& token);
    static std::string loadTokenMac(const std::string& username);
    static bool deleteTokenMac(const std::string& username);
    static bool hasTokenMac(const std::string& username);
#elif __linux__
    // Linux-specific implementation
    static bool saveTokenLinux(const std::string& username, const std::string& token);
    static std::string loadTokenLinux(const std::string& username);
    static bool deleteTokenLinux(const std::string& username);
    static bool hasTokenLinux(const std::string& username);
#endif
};

} // namespace baludesk

#include "credential_store.h"
#include "logger.h"
#include <vector>

// Platform-specific includes
#ifdef _WIN32
    #include <windows.h>
    #include <wincred.h>
    #pragma comment(lib, "Advapi32.lib")
#elif __APPLE__
    #include <Security/Security.h>
    #include <CoreFoundation/CoreFoundation.h>
#elif __linux__
    #include <libsecret/secret.h>
#endif

namespace baludesk {

// ============================================================================
// Public Interface (Platform-agnostic)
// ============================================================================

bool CredentialStore::saveToken(const std::string& username, const std::string& token) {
    if (username.empty() || token.empty()) {
        Logger::error("CredentialStore: Cannot save empty username or token");
        return false;
    }

#ifdef _WIN32
    return saveTokenWindows(username, token);
#elif __APPLE__
    return saveTokenMac(username, token);
#elif __linux__
    return saveTokenLinux(username, token);
#else
    Logger::error("CredentialStore: Unsupported platform");
    return false;
#endif
}

std::string CredentialStore::loadToken(const std::string& username) {
    if (username.empty()) {
        Logger::error("CredentialStore: Cannot load token for empty username");
        return "";
    }

#ifdef _WIN32
    return loadTokenWindows(username);
#elif __APPLE__
    return loadTokenMac(username);
#elif __linux__
    return loadTokenLinux(username);
#else
    Logger::error("CredentialStore: Unsupported platform");
    return "";
#endif
}

bool CredentialStore::deleteToken(const std::string& username) {
    if (username.empty()) {
        Logger::error("CredentialStore: Cannot delete token for empty username");
        return false;
    }

#ifdef _WIN32
    return deleteTokenWindows(username);
#elif __APPLE__
    return deleteTokenMac(username);
#elif __linux__
    return deleteTokenLinux(username);
#else
    Logger::error("CredentialStore: Unsupported platform");
    return false;
#endif
}

bool CredentialStore::hasToken(const std::string& username) {
    if (username.empty()) {
        return false;
    }

#ifdef _WIN32
    return hasTokenWindows(username);
#elif __APPLE__
    return hasTokenMac(username);
#elif __linux__
    return hasTokenLinux(username);
#else
    return false;
#endif
}

// ============================================================================
// Windows Implementation (Credential Manager)
// ============================================================================

#ifdef _WIN32

bool CredentialStore::saveTokenWindows(const std::string& username, const std::string& token) {
    // Convert target name to wide string
    std::wstring targetName = std::wstring(SERVICE_NAME, SERVICE_NAME + strlen(SERVICE_NAME)) +
                              L"_" +
                              std::wstring(username.begin(), username.end());

    // Convert username to wide string
    std::wstring usernameW(username.begin(), username.end());

    // Prepare credential structure
    CREDENTIALW cred = {0};
    cred.Type = CRED_TYPE_GENERIC;
    cred.TargetName = const_cast<LPWSTR>(targetName.c_str());
    cred.UserName = const_cast<LPWSTR>(usernameW.c_str());
    cred.CredentialBlobSize = static_cast<DWORD>(token.size());
    cred.CredentialBlob = reinterpret_cast<LPBYTE>(const_cast<char*>(token.data()));
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE;

    if (CredWriteW(&cred, 0) != TRUE) {
        DWORD error = GetLastError();
        Logger::error("CredentialStore(Windows): Failed to save token, error code: {}", error);
        return false;
    }

    Logger::info("CredentialStore(Windows): Token saved successfully for user: {}", username);
    return true;
}

std::string CredentialStore::loadTokenWindows(const std::string& username) {
    // Convert target name to wide string
    std::wstring targetName = std::wstring(SERVICE_NAME, SERVICE_NAME + strlen(SERVICE_NAME)) +
                              L"_" +
                              std::wstring(username.begin(), username.end());

    PCREDENTIALW pcred = nullptr;

    if (CredReadW(targetName.c_str(), CRED_TYPE_GENERIC, 0, &pcred) != TRUE) {
        DWORD error = GetLastError();
        if (error != ERROR_NOT_FOUND) {
            Logger::error("CredentialStore(Windows): Failed to load token, error code: {}", error);
        }
        return "";
    }

    // Extract token from credential blob
    std::string token(
        reinterpret_cast<char*>(pcred->CredentialBlob),
        pcred->CredentialBlobSize
    );

    CredFree(pcred);

    Logger::debug("CredentialStore(Windows): Token loaded successfully for user: {}", username);
    return token;
}

bool CredentialStore::deleteTokenWindows(const std::string& username) {
    // Convert target name to wide string
    std::wstring targetName = std::wstring(SERVICE_NAME, SERVICE_NAME + strlen(SERVICE_NAME)) +
                              L"_" +
                              std::wstring(username.begin(), username.end());

    if (CredDeleteW(targetName.c_str(), CRED_TYPE_GENERIC, 0) != TRUE) {
        DWORD error = GetLastError();
        if (error != ERROR_NOT_FOUND) {
            Logger::error("CredentialStore(Windows): Failed to delete token, error code: {}", error);
            return false;
        }
    }

    Logger::info("CredentialStore(Windows): Token deleted successfully for user: {}", username);
    return true;
}

bool CredentialStore::hasTokenWindows(const std::string& username) {
    // Convert target name to wide string
    std::wstring targetName = std::wstring(SERVICE_NAME, SERVICE_NAME + strlen(SERVICE_NAME)) +
                              L"_" +
                              std::wstring(username.begin(), username.end());

    PCREDENTIALW pcred = nullptr;

    if (CredReadW(targetName.c_str(), CRED_TYPE_GENERIC, 0, &pcred) != TRUE) {
        return false;
    }

    CredFree(pcred);
    return true;
}

#endif // _WIN32

// ============================================================================
// macOS Implementation (Keychain Services)
// ============================================================================

#ifdef __APPLE__

bool CredentialStore::saveTokenMac(const std::string& username, const std::string& token) {
    // First, try to delete existing token (update)
    deleteTokenMac(username);

    OSStatus status = SecKeychainAddGenericPassword(
        NULL,                                          // default keychain
        static_cast<UInt32>(strlen(SERVICE_NAME)),     // service name length
        SERVICE_NAME,                                  // service name
        static_cast<UInt32>(username.size()),          // account name length
        username.c_str(),                              // account name
        static_cast<UInt32>(token.size()),             // password length
        token.c_str(),                                 // password data
        NULL                                           // item reference (not needed)
    );

    if (status != errSecSuccess) {
        Logger::error("CredentialStore(macOS): Failed to save token, OSStatus: {}", status);
        return false;
    }

    Logger::info("CredentialStore(macOS): Token saved successfully for user: {}", username);
    return true;
}

std::string CredentialStore::loadTokenMac(const std::string& username) {
    void* passwordData = nullptr;
    UInt32 passwordLength = 0;

    OSStatus status = SecKeychainFindGenericPassword(
        NULL,                                          // default keychain
        static_cast<UInt32>(strlen(SERVICE_NAME)),     // service name length
        SERVICE_NAME,                                  // service name
        static_cast<UInt32>(username.size()),          // account name length
        username.c_str(),                              // account name
        &passwordLength,                               // password length (out)
        &passwordData,                                 // password data (out)
        NULL                                           // item reference (not needed)
    );

    if (status != errSecSuccess) {
        if (status != errSecItemNotFound) {
            Logger::error("CredentialStore(macOS): Failed to load token, OSStatus: {}", status);
        }
        return "";
    }

    // Copy password to string and free keychain memory
    std::string token(static_cast<char*>(passwordData), passwordLength);
    SecKeychainItemFreeContent(NULL, passwordData);

    Logger::debug("CredentialStore(macOS): Token loaded successfully for user: {}", username);
    return token;
}

bool CredentialStore::deleteTokenMac(const std::string& username) {
    SecKeychainItemRef itemRef = nullptr;

    OSStatus status = SecKeychainFindGenericPassword(
        NULL,                                          // default keychain
        static_cast<UInt32>(strlen(SERVICE_NAME)),     // service name length
        SERVICE_NAME,                                  // service name
        static_cast<UInt32>(username.size()),          // account name length
        username.c_str(),                              // account name
        NULL,                                          // password length (not needed)
        NULL,                                          // password data (not needed)
        &itemRef                                       // item reference (needed for delete)
    );

    if (status != errSecSuccess) {
        if (status != errSecItemNotFound) {
            Logger::error("CredentialStore(macOS): Failed to find token for deletion, OSStatus: {}", status);
            return false;
        }
        return true; // Not found is success for delete
    }

    status = SecKeychainItemDelete(itemRef);
    CFRelease(itemRef);

    if (status != errSecSuccess) {
        Logger::error("CredentialStore(macOS): Failed to delete token, OSStatus: {}", status);
        return false;
    }

    Logger::info("CredentialStore(macOS): Token deleted successfully for user: {}", username);
    return true;
}

bool CredentialStore::hasTokenMac(const std::string& username) {
    OSStatus status = SecKeychainFindGenericPassword(
        NULL,                                          // default keychain
        static_cast<UInt32>(strlen(SERVICE_NAME)),     // service name length
        SERVICE_NAME,                                  // service name
        static_cast<UInt32>(username.size()),          // account name length
        username.c_str(),                              // account name
        NULL,                                          // password length (not needed)
        NULL,                                          // password data (not needed)
        NULL                                           // item reference (not needed)
    );

    return status == errSecSuccess;
}

#endif // __APPLE__

// ============================================================================
// Linux Implementation (libsecret)
// ============================================================================

#ifdef __linux__

// libsecret schema definition
static const SecretSchema* getSchema() {
    static const SecretSchema schema = {
        "com.baluhost.baludesk",                       // schema name
        SECRET_SCHEMA_NONE,
        {
            { "username", SECRET_SCHEMA_ATTRIBUTE_STRING },
            { "service", SECRET_SCHEMA_ATTRIBUTE_STRING },
            { "NULL", SECRET_SCHEMA_ATTRIBUTE_STRING }
        }
    };
    return &schema;
}

bool CredentialStore::saveTokenLinux(const std::string& username, const std::string& token) {
    GError* error = nullptr;

    secret_password_store_sync(
        getSchema(),                                   // schema
        SECRET_COLLECTION_DEFAULT,                     // collection
        "BaluDesk Token",                              // label
        token.c_str(),                                 // password
        NULL,                                          // cancellable
        &error,                                        // error
        "service", SERVICE_NAME,                       // attributes
        "username", username.c_str(),
        NULL
    );

    if (error != nullptr) {
        Logger::error("CredentialStore(Linux): Failed to save token: {}", error->message);
        g_error_free(error);
        return false;
    }

    Logger::info("CredentialStore(Linux): Token saved successfully for user: {}", username);
    return true;
}

std::string CredentialStore::loadTokenLinux(const std::string& username) {
    GError* error = nullptr;

    gchar* password = secret_password_lookup_sync(
        getSchema(),                                   // schema
        NULL,                                          // cancellable
        &error,                                        // error
        "service", SERVICE_NAME,                       // attributes
        "username", username.c_str(),
        NULL
    );

    if (error != nullptr) {
        Logger::error("CredentialStore(Linux): Failed to load token: {}", error->message);
        g_error_free(error);
        return "";
    }

    if (password == nullptr) {
        return "";
    }

    std::string token(password);
    secret_password_free(password);

    Logger::debug("CredentialStore(Linux): Token loaded successfully for user: {}", username);
    return token;
}

bool CredentialStore::deleteTokenLinux(const std::string& username) {
    GError* error = nullptr;

    gboolean result = secret_password_clear_sync(
        getSchema(),                                   // schema
        NULL,                                          // cancellable
        &error,                                        // error
        "service", SERVICE_NAME,                       // attributes
        "username", username.c_str(),
        NULL
    );

    if (error != nullptr) {
        Logger::error("CredentialStore(Linux): Failed to delete token: {}", error->message);
        g_error_free(error);
        return false;
    }

    if (result == FALSE) {
        Logger::warn("CredentialStore(Linux): Token not found for deletion: {}", username);
    } else {
        Logger::info("CredentialStore(Linux): Token deleted successfully for user: {}", username);
    }

    return true;
}

bool CredentialStore::hasTokenLinux(const std::string& username) {
    GError* error = nullptr;

    gchar* password = secret_password_lookup_sync(
        getSchema(),                                   // schema
        NULL,                                          // cancellable
        &error,                                        // error
        "service", SERVICE_NAME,                       // attributes
        "username", username.c_str(),
        NULL
    );

    if (error != nullptr) {
        g_error_free(error);
        return false;
    }

    if (password != nullptr) {
        secret_password_free(password);
        return true;
    }

    return false;
}

#endif // __linux__

} // namespace baludesk

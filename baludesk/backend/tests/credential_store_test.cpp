#include <gtest/gtest.h>
#include "../src/utils/credential_store.h"
#include "../src/utils/logger.h"
#include <string>

using namespace baludesk;

class CredentialStoreTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize logger for tests
        Logger::initialize("credential_store_test.log", true);

        // Clean up any existing test credentials
        CredentialStore::deleteToken("test_user");
        CredentialStore::deleteToken("another_user");
    }

    void TearDown() override {
        // Clean up test credentials
        CredentialStore::deleteToken("test_user");
        CredentialStore::deleteToken("another_user");
    }
};

// ============================================================================
// Basic Functionality Tests
// ============================================================================

TEST_F(CredentialStoreTest, SaveAndLoadToken) {
    const std::string username = "test_user";
    const std::string token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test_token";

    // Save token
    ASSERT_TRUE(CredentialStore::saveToken(username, token));

    // Load token
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_EQ(token, loadedToken);
}

TEST_F(CredentialStoreTest, LoadNonExistentToken) {
    const std::string username = "nonexistent_user";

    // Try to load token that doesn't exist
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_TRUE(loadedToken.empty());
}

TEST_F(CredentialStoreTest, DeleteToken) {
    const std::string username = "test_user";
    const std::string token = "test_token_123";

    // Save token
    ASSERT_TRUE(CredentialStore::saveToken(username, token));

    // Verify it exists
    EXPECT_TRUE(CredentialStore::hasToken(username));

    // Delete token
    ASSERT_TRUE(CredentialStore::deleteToken(username));

    // Verify it's gone
    EXPECT_FALSE(CredentialStore::hasToken(username));

    // Try to load deleted token
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_TRUE(loadedToken.empty());
}

TEST_F(CredentialStoreTest, DeleteNonExistentToken) {
    const std::string username = "nonexistent_user";

    // Deleting non-existent token should succeed (idempotent)
    EXPECT_TRUE(CredentialStore::deleteToken(username));
}

TEST_F(CredentialStoreTest, HasToken) {
    const std::string username = "test_user";
    const std::string token = "test_token_456";

    // Initially no token
    EXPECT_FALSE(CredentialStore::hasToken(username));

    // Save token
    ASSERT_TRUE(CredentialStore::saveToken(username, token));

    // Now token exists
    EXPECT_TRUE(CredentialStore::hasToken(username));

    // Delete token
    ASSERT_TRUE(CredentialStore::deleteToken(username));

    // Token gone again
    EXPECT_FALSE(CredentialStore::hasToken(username));
}

// ============================================================================
// Edge Cases
// ============================================================================

TEST_F(CredentialStoreTest, SaveEmptyUsername) {
    const std::string token = "test_token";

    // Should fail to save with empty username
    EXPECT_FALSE(CredentialStore::saveToken("", token));
}

TEST_F(CredentialStoreTest, SaveEmptyToken) {
    const std::string username = "test_user";

    // Should fail to save with empty token
    EXPECT_FALSE(CredentialStore::saveToken(username, ""));
}

TEST_F(CredentialStoreTest, LoadEmptyUsername) {
    // Should return empty string for empty username
    std::string loadedToken = CredentialStore::loadToken("");
    EXPECT_TRUE(loadedToken.empty());
}

TEST_F(CredentialStoreTest, LongToken) {
    const std::string username = "test_user";
    // Generate a long token (4KB)
    std::string longToken(4096, 'a');
    longToken += ".very_long_jwt_token.signature";

    // Save long token
    ASSERT_TRUE(CredentialStore::saveToken(username, longToken));

    // Load and verify
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_EQ(longToken, loadedToken);
    EXPECT_EQ(longToken.size(), loadedToken.size());
}

TEST_F(CredentialStoreTest, SpecialCharactersInUsername) {
    const std::string username = "test@user.com";
    const std::string token = "test_token_789";

    // Save token
    ASSERT_TRUE(CredentialStore::saveToken(username, token));

    // Load token
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_EQ(token, loadedToken);

    // Clean up
    ASSERT_TRUE(CredentialStore::deleteToken(username));
}

TEST_F(CredentialStoreTest, SpecialCharactersInToken) {
    const std::string username = "test_user";
    const std::string token = "token!@#$%^&*()_+-=[]{}|;':\",./<>?`~";

    // Save token with special characters
    ASSERT_TRUE(CredentialStore::saveToken(username, token));

    // Load and verify
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_EQ(token, loadedToken);
}

TEST_F(CredentialStoreTest, UnicodeInToken) {
    const std::string username = "test_user";
    const std::string token = "token_with_unicode_äöü_🔑_test";

    // Save token with unicode
    ASSERT_TRUE(CredentialStore::saveToken(username, token));

    // Load and verify
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_EQ(token, loadedToken);
}

// ============================================================================
// Multi-User Tests
// ============================================================================

TEST_F(CredentialStoreTest, MultipleUsers) {
    const std::string user1 = "user1";
    const std::string token1 = "token_for_user1";
    const std::string user2 = "user2";
    const std::string token2 = "token_for_user2";

    // Save tokens for both users
    ASSERT_TRUE(CredentialStore::saveToken(user1, token1));
    ASSERT_TRUE(CredentialStore::saveToken(user2, token2));

    // Load and verify both tokens
    EXPECT_EQ(token1, CredentialStore::loadToken(user1));
    EXPECT_EQ(token2, CredentialStore::loadToken(user2));

    // Delete user1's token
    ASSERT_TRUE(CredentialStore::deleteToken(user1));

    // user2's token should still exist
    EXPECT_FALSE(CredentialStore::hasToken(user1));
    EXPECT_TRUE(CredentialStore::hasToken(user2));
    EXPECT_EQ(token2, CredentialStore::loadToken(user2));

    // Clean up
    ASSERT_TRUE(CredentialStore::deleteToken(user2));
}

// ============================================================================
// Update Tests
// ============================================================================

TEST_F(CredentialStoreTest, UpdateToken) {
    const std::string username = "test_user";
    const std::string oldToken = "old_token_123";
    const std::string newToken = "new_token_456";

    // Save old token
    ASSERT_TRUE(CredentialStore::saveToken(username, oldToken));
    EXPECT_EQ(oldToken, CredentialStore::loadToken(username));

    // Update with new token (overwrite)
    ASSERT_TRUE(CredentialStore::saveToken(username, newToken));

    // Load and verify new token
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_EQ(newToken, loadedToken);
    EXPECT_NE(oldToken, loadedToken);
}

// ============================================================================
// Real-World Scenario Tests
// ============================================================================

TEST_F(CredentialStoreTest, JWTTokenRoundtrip) {
    const std::string username = "admin@baluhost.com";
    const std::string jwtToken =
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c";

    // Save JWT
    ASSERT_TRUE(CredentialStore::saveToken(username, jwtToken));

    // Load JWT
    std::string loadedToken = CredentialStore::loadToken(username);
    EXPECT_EQ(jwtToken, loadedToken);

    // Verify character-by-character (ensure no corruption)
    ASSERT_EQ(jwtToken.size(), loadedToken.size());
    for (size_t i = 0; i < jwtToken.size(); ++i) {
        EXPECT_EQ(jwtToken[i], loadedToken[i]) << "Mismatch at index " << i;
    }
}

TEST_F(CredentialStoreTest, LoginLogoutFlow) {
    const std::string username = "test_user";
    const std::string token = "session_token_xyz";

    // Simulate login
    ASSERT_TRUE(CredentialStore::saveToken(username, token));
    EXPECT_TRUE(CredentialStore::hasToken(username));

    // Simulate session validation
    std::string sessionToken = CredentialStore::loadToken(username);
    EXPECT_EQ(token, sessionToken);

    // Simulate logout
    ASSERT_TRUE(CredentialStore::deleteToken(username));
    EXPECT_FALSE(CredentialStore::hasToken(username));

    // Simulate failed authentication after logout
    std::string noToken = CredentialStore::loadToken(username);
    EXPECT_TRUE(noToken.empty());
}

// ============================================================================
// Performance Tests
// ============================================================================

TEST_F(CredentialStoreTest, PerformanceSaveLoad100Times) {
    const std::string username = "perf_test_user";
    const std::string token = "performance_test_token";

    auto start = std::chrono::steady_clock::now();

    // Save and load 100 times
    for (int i = 0; i < 100; ++i) {
        ASSERT_TRUE(CredentialStore::saveToken(username, token));
        std::string loadedToken = CredentialStore::loadToken(username);
        EXPECT_EQ(token, loadedToken);
    }

    auto end = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);

    // Should complete in reasonable time (< 5 seconds for 100 operations)
    EXPECT_LT(duration.count(), 5000) << "100 save/load operations took " << duration.count() << "ms";

    // Clean up
    ASSERT_TRUE(CredentialStore::deleteToken(username));
}

// ============================================================================
// Platform-Specific Tests (informational)
// ============================================================================

TEST_F(CredentialStoreTest, PlatformInfo) {
#ifdef _WIN32
    std::cout << "[INFO] Running on Windows - using Credential Manager" << std::endl;
#elif __APPLE__
    std::cout << "[INFO] Running on macOS - using Keychain Services" << std::endl;
#elif __linux__
    std::cout << "[INFO] Running on Linux - using libsecret" << std::endl;
#else
    std::cout << "[WARNING] Unknown platform!" << std::endl;
#endif
}

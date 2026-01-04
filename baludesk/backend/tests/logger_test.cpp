#include <gtest/gtest.h>
#include "utils/logger.h"
#include <filesystem>
#include <thread>
#include <chrono>

// Test fixture for Logger tests
class LoggerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Create temp log directory
        testLogDir_ = std::filesystem::temp_directory_path() / "baludesk_test_logs";
        std::filesystem::create_directories(testLogDir_);
        
        testLogFile_ = (testLogDir_ / "test.log").string();
        
        // Initialize logger
        baludesk::Logger::initialize(testLogFile_, true);
    }

    void TearDown() override {
        // CRITICAL: Shutdown logger BEFORE deleting directories
        baludesk::Logger::shutdown();
        
        // Small delay to ensure Windows releases file handles
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        
        // Clean up log files
        if (std::filesystem::exists(testLogDir_)) {
            std::error_code ec;
            std::filesystem::remove_all(testLogDir_, ec);
            // Ignore errors on cleanup - test already passed/failed
        }
    }

    std::filesystem::path testLogDir_;
    std::string testLogFile_;
};

// Test basic logging
TEST_F(LoggerTest, BasicLogging) {
    ASSERT_NO_THROW(baludesk::Logger::info("Test info message"));
    ASSERT_NO_THROW(baludesk::Logger::warn("Test warning message"));
    ASSERT_NO_THROW(baludesk::Logger::error("Test error message"));
}

// Test format string logging
TEST_F(LoggerTest, FormatLogging) {
    ASSERT_NO_THROW(baludesk::Logger::info("User {} logged in", "testuser"));
    ASSERT_NO_THROW(baludesk::Logger::debug("Processing file: {}", "/path/to/file.txt"));
    ASSERT_NO_THROW(baludesk::Logger::warn("Failed {} out of {} attempts", 3, 5));
}

// Test log file creation
TEST_F(LoggerTest, LogFileCreated) {
    baludesk::Logger::info("Test message");
    baludesk::Logger::shutdown();
    
    ASSERT_TRUE(std::filesystem::exists(testLogFile_));
    ASSERT_GT(std::filesystem::file_size(testLogFile_), 0);
}

// Test multiple log levels
TEST_F(LoggerTest, AllLevels) {
    ASSERT_NO_THROW({
        baludesk::Logger::trace("Trace message");
        baludesk::Logger::debug("Debug message");
        baludesk::Logger::info("Info message");
        baludesk::Logger::warn("Warning message");
        baludesk::Logger::error("Error message");
        baludesk::Logger::critical("Critical message");
    });
}

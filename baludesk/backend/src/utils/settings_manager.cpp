#include "settings_manager.h"
#include "logger.h"
#include <fstream>
#include <filesystem>

namespace baludesk {

SettingsManager& SettingsManager::getInstance() {
    static SettingsManager instance;
    return instance;
}

SettingsManager::SettingsManager() {
    std::filesystem::path appDataPath;
    
    #ifdef _WIN32
    const char* appDataEnv = std::getenv("APPDATA");
    appDataPath = appDataEnv ? appDataEnv : ".";
    #else
    const char* homeEnv = std::getenv("HOME");
    appDataPath = homeEnv ? homeEnv : ".";
    appDataPath /= ".config";
    #endif
    
    appDataPath /= "BaluDesk";
    
    // Create directory if it doesn't exist
    std::filesystem::create_directories(appDataPath);
    
    settingsPath_ = (appDataPath / "settings.json").string();
    
    // Initialize with defaults
    initializeDefaults();
    
    // Try to load from file
    loadSettings();
}

void SettingsManager::initializeDefaults() {
    settings_ = nlohmann::json{
        // Server Connection
        {"serverUrl", "http://localhost"},
        {"serverPort", 8000},
        {"username", ""},
        {"rememberPassword", false},
        
        // Sync Behavior
        {"autoStartSync", true},
        {"syncInterval", 60},
        {"maxConcurrentTransfers", 4},
        {"bandwidthLimitMbps", 0},
        {"conflictResolution", "ask"},
        
        // UI Preferences
        {"theme", "dark"},
        {"language", "en"},
        {"startMinimized", false},
        {"showNotifications", true},
        {"notifyOnSyncComplete", true},
        {"notifyOnErrors", true},
        
        // Advanced
        {"enableDebugLogging", false},
        {"chunkSizeMb", 10}
    };
}

bool SettingsManager::loadSettings() {
    try {
        if (!std::filesystem::exists(settingsPath_)) {
            Logger::info("Settings file not found, using defaults: {}", settingsPath_);
            return true;
        }
        
        std::ifstream file(settingsPath_);
        if (!file.is_open()) {
            Logger::warn("Failed to open settings file: {}", settingsPath_);
            return false;
        }
        
        nlohmann::json loaded = nlohmann::json::parse(file);
        
        // Merge loaded settings with defaults (preserve defaults for missing keys)
        for (auto& [key, value] : loaded.items()) {
            if (settings_.contains(key)) {
                settings_[key] = value;
            }
        }
        
        Logger::info("Settings loaded successfully from: {}", settingsPath_);
        return true;
    } catch (const std::exception& e) {
        Logger::error("Failed to load settings: {}", e.what());
        return false;
    }
}

bool SettingsManager::saveSettings() {
    try {
        std::ofstream file(settingsPath_);
        if (!file.is_open()) {
            Logger::error("Failed to open settings file for writing: {}", settingsPath_);
            return false;
        }
        
        file << settings_.dump(2);
        file.close();
        
        Logger::info("Settings saved successfully to: {}", settingsPath_);
        return true;
    } catch (const std::exception& e) {
        Logger::error("Failed to save settings: {}", e.what());
        return false;
    }
}

nlohmann::json SettingsManager::getSettings() const {
    return settings_;
}

bool SettingsManager::updateSettings(const nlohmann::json& updates) {
    try {
        // Validate all keys are known
        for (auto& [key, value] : updates.items()) {
            if (!settings_.contains(key)) {
                Logger::warn("Unknown settings key: {}", key);
                continue;
            }
            settings_[key] = value;
        }
        
        // Save to file
        if (saveSettings()) {
            Logger::info("Settings updated: {} keys", updates.size());
            return true;
        }
        return false;
    } catch (const std::exception& e) {
        Logger::error("Failed to update settings: {}", e.what());
        return false;
    }
}

// Getters
std::string SettingsManager::getServerUrl() const {
    return settings_.value("serverUrl", "http://localhost");
}

int SettingsManager::getServerPort() const {
    return settings_.value("serverPort", 8000);
}

std::string SettingsManager::getUsername() const {
    return settings_.value("username", "");
}

bool SettingsManager::isAutoStartSyncEnabled() const {
    return settings_.value("autoStartSync", true);
}

int SettingsManager::getSyncInterval() const {
    return settings_.value("syncInterval", 60);
}

int SettingsManager::getMaxConcurrentTransfers() const {
    return settings_.value("maxConcurrentTransfers", 4);
}

int SettingsManager::getBandwidthLimitMbps() const {
    return settings_.value("bandwidthLimitMbps", 0);
}

std::string SettingsManager::getConflictResolution() const {
    return settings_.value("conflictResolution", "ask");
}

std::string SettingsManager::getTheme() const {
    return settings_.value("theme", "dark");
}

bool SettingsManager::isDebugLoggingEnabled() const {
    return settings_.value("enableDebugLogging", false);
}

int SettingsManager::getChunkSizeMb() const {
    return settings_.value("chunkSizeMb", 10);
}

}  // namespace baludesk

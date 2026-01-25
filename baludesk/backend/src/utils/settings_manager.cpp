#include "settings_manager.h"
#include "logger.h"
#include <fstream>
#include <filesystem>
#include <chrono>
#include <cstdlib>
#include <ctime>

#ifdef _WIN32
#include <windows.h>
#include <objbase.h>
#else
#include <unistd.h>
#endif

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
        {"chunkSizeMb", 10},

        // Device Registration
        {"deviceId", ""},
        {"deviceName", ""},
        {"deviceRegistered", false}
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

// Device Registration
std::string SettingsManager::getDeviceId() {
    std::string deviceId = settings_.value("deviceId", "");

    // Generate and save if not exists
    if (deviceId.empty()) {
        deviceId = generateDeviceId();
        settings_["deviceId"] = deviceId;
        saveSettings();
        Logger::info("Generated new device ID: {}", deviceId);
    }

    return deviceId;
}

std::string SettingsManager::getDeviceName() const {
    std::string name = settings_.value("deviceName", "");

    // Return hostname as fallback if name not set
    if (name.empty()) {
        return const_cast<SettingsManager*>(this)->getSystemHostname();
    }

    return name;
}

void SettingsManager::setDeviceName(const std::string& name) {
    settings_["deviceName"] = name;
    saveSettings();
    Logger::info("Device name updated: {}", name);
}

bool SettingsManager::isDeviceRegistered() const {
    return settings_.value("deviceRegistered", false);
}

void SettingsManager::setDeviceRegistered(bool registered) {
    settings_["deviceRegistered"] = registered;
    saveSettings();
    Logger::info("Device registration status: {}", registered ? "registered" : "unregistered");
}

std::string SettingsManager::generateDeviceId() {
    // Generate UUID v4 using platform-specific methods
    std::string uuid;

    #ifdef _WIN32
    // Windows: Use CoCreateGuid
    #include <objbase.h>
    GUID guid;
    if (CoCreateGuid(&guid) == S_OK) {
        char buffer[40];
        snprintf(buffer, sizeof(buffer),
                "%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x",
                guid.Data1, guid.Data2, guid.Data3,
                guid.Data4[0], guid.Data4[1], guid.Data4[2], guid.Data4[3],
                guid.Data4[4], guid.Data4[5], guid.Data4[6], guid.Data4[7]);
        uuid = buffer;
    }
    #else
    // Linux/macOS: Read from /proc/sys/kernel/random/uuid or use uuidgen
    std::ifstream uuidFile("/proc/sys/kernel/random/uuid");
    if (uuidFile.is_open()) {
        std::getline(uuidFile, uuid);
        uuidFile.close();
    } else {
        // Fallback: Try uuidgen command
        FILE* pipe = popen("uuidgen", "r");
        if (pipe) {
            char buffer[40];
            if (fgets(buffer, sizeof(buffer), pipe)) {
                uuid = buffer;
                // Remove newline
                if (!uuid.empty() && uuid.back() == '\n') {
                    uuid.pop_back();
                }
            }
            pclose(pipe);
        }
    }
    #endif

    // Fallback to timestamp-based UUID if platform methods fail
    if (uuid.empty()) {
        auto now = std::chrono::system_clock::now();
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();

        // Simple pseudo-UUID format
        char buffer[40];
        snprintf(buffer, sizeof(buffer),
                "baludesk-%016llx-%04x",
                (unsigned long long)ms,
                rand() % 0xFFFF);
        uuid = buffer;
    }

    return uuid;
}

std::string SettingsManager::getSystemHostname() {
    char hostname[256] = {0};

    #ifdef _WIN32
    DWORD size = sizeof(hostname);
    if (GetComputerNameA(hostname, &size)) {
        return std::string(hostname);
    }
    #else
    if (gethostname(hostname, sizeof(hostname)) == 0) {
        return std::string(hostname);
    }
    #endif

    return "BaluDesk-Device";
}

}  // namespace baludesk

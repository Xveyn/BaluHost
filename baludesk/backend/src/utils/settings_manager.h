#pragma once

#include <string>
#include <nlohmann/json.hpp>

namespace baludesk {

class SettingsManager {
public:
    static SettingsManager& getInstance();
    
    // Load settings from file
    bool loadSettings();
    
    // Save settings to file
    bool saveSettings();
    
    // Get/Set individual settings
    nlohmann::json getSettings() const;
    bool updateSettings(const nlohmann::json& updates);
    
    // Getters for common settings
    std::string getServerUrl() const;
    int getServerPort() const;
    std::string getUsername() const;
    bool isAutoStartSyncEnabled() const;
    int getSyncInterval() const;
    int getMaxConcurrentTransfers() const;
    int getBandwidthLimitMbps() const;
    std::string getConflictResolution() const;
    std::string getTheme() const;
    bool isDebugLoggingEnabled() const;
    int getChunkSizeMb() const;

private:
    SettingsManager();
    ~SettingsManager() = default;
    
    // Prevent copy/move
    SettingsManager(const SettingsManager&) = delete;
    SettingsManager& operator=(const SettingsManager&) = delete;
    
    nlohmann::json settings_;
    std::string settingsPath_;
    
    // Initialize with default settings
    void initializeDefaults();
    
    // Validate settings structure
    bool validateSettings(const nlohmann::json& settings);
};

}  // namespace baludesk

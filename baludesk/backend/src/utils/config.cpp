#include "config.h"
#include "../utils/logger.h"
#include <nlohmann/json.hpp>
#include <fstream>
#include <sstream>

using json = nlohmann::json;

namespace baludesk {

Config::Config() 
    : serverUrl_("http://localhost:8000"), 
      databasePath_("baludesk.db") {
}

bool Config::load(const std::string& configPath) {
    Logger::info("Loading configuration from: {}", configPath);
    
    try {
        std::ifstream configFile(configPath);
        if (!configFile.is_open()) {
            Logger::warn("Config file not found: {}", configPath);
            return false;
        }
        
        json configJson;
        configFile >> configJson;
        
        if (configJson.contains("server_url")) {
            serverUrl_ = configJson["server_url"].get<std::string>();
        }
        
        if (configJson.contains("database_path")) {
            databasePath_ = configJson["database_path"].get<std::string>();
        }
        
        Logger::info("Configuration loaded successfully");
        Logger::debug("Server URL: {}", serverUrl_);
        Logger::debug("Database path: {}", databasePath_);
        
        return true;
        
    } catch (const std::exception& e) {
        Logger::error("Failed to load config: {}", e.what());
        return false;
    }
}

std::string Config::getDatabasePath() const {
    return databasePath_;
}

std::string Config::getServerUrl() const {
    return serverUrl_;
}

} // namespace baludesk

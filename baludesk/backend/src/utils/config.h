#pragma once

#include <string>

namespace baludesk {

class Config {
public:
    Config();
    
    bool load(const std::string& configPath);
    
    std::string getDatabasePath() const;
    std::string getServerUrl() const;

private:
    std::string serverUrl_;
    std::string databasePath_;
};

} // namespace baludesk

#pragma once

#include <nlohmann/json.hpp>
#include <string>

namespace baludesk {

// Forward declaration
class SyncEngine;

class IpcServer {
public:
    explicit IpcServer(SyncEngine* engine);
    
    bool start();
    void stop();
    void processMessages();
    
    // Broadcast events to Electron frontend
    void broadcastEvent(const std::string& eventType, const nlohmann::json& data);

private:
    void handlePing(int requestId = -1);
    void handleLogin(const nlohmann::json& message, int requestId = -1);
    void handleAddSyncFolder(const nlohmann::json& message, int requestId = -1);
    void handleRemoveSyncFolder(const nlohmann::json& message, int requestId = -1);
    void handlePauseSync(const nlohmann::json& message, int requestId = -1);
    void handleResumeSync(const nlohmann::json& message, int requestId = -1);
    void handleGetSyncState(int requestId = -1);
    void handleGetFolders(int requestId = -1);
    
    void sendResponse(const nlohmann::json& response, int requestId = -1);
    void sendError(const std::string& error, int requestId = -1);

    SyncEngine* engine_;
};

} // namespace baludesk

#pragma once

#include <nlohmann/json.hpp>
#include <string>
#include <memory>

namespace baludesk {

// Forward declarations
class SyncEngine;
class BaluhostClient;

class IpcServer {
public:
    explicit IpcServer(SyncEngine* engine);
    ~IpcServer();
    
    bool start();
    void stop();
    void processMessages();
    
    // Broadcast events to Electron frontend
    void broadcastEvent(const std::string& eventType, const nlohmann::json& data);

private:
    // Sync handlers
    void handlePing(int requestId = -1);
    void handleLogin(const nlohmann::json& message, int requestId = -1);
    void handleAddSyncFolder(const nlohmann::json& message, int requestId = -1);
    void handleRemoveSyncFolder(const nlohmann::json& message, int requestId = -1);
    void handlePauseSync(const nlohmann::json& message, int requestId = -1);
    void handleResumeSync(const nlohmann::json& message, int requestId = -1);
    void handleUpdateSyncFolder(const nlohmann::json& message, int requestId = -1);
    void handleGetSyncState(int requestId = -1);
    void handleGetFolders(int requestId = -1);
    
    // System info handler
    void handleGetSystemInfo(int requestId = -1);
    
    // RAID info handler
    void handleGetRaidStatus(int requestId = -1);
    
    // File operation handlers
    void handleListFiles(const nlohmann::json& message, int requestId = -1);
    void handleGetMountpoints(int requestId = -1);
    void handleCreateFolder(const nlohmann::json& message, int requestId = -1);
    void handleRenameFile(const nlohmann::json& message, int requestId = -1);
    void handleMoveFile(const nlohmann::json& message, int requestId = -1);
    void handleDeleteFile(const nlohmann::json& message, int requestId = -1);
    void handleDownloadFile(const nlohmann::json& message, int requestId = -1);
    void handleUploadFile(const nlohmann::json& message, int requestId = -1);
    void handleGetPermissions(const nlohmann::json& message, int requestId = -1);
    void handleSetPermission(const nlohmann::json& message, int requestId = -1);
    void handleRemovePermission(const nlohmann::json& message, int requestId = -1);
    
    // Settings handlers
    void handleGetSettings(const nlohmann::json& message, int requestId = -1);
    void handleUpdateSettings(const nlohmann::json& message, int requestId = -1);
    
    void sendResponse(const nlohmann::json& response, int requestId = -1);
    void sendError(const std::string& error, int requestId = -1);

    SyncEngine* engine_;
    std::unique_ptr<BaluhostClient> baluhostClient_;
};

} // namespace baludesk

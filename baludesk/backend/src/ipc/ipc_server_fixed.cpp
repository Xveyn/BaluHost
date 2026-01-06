#include "ipc_server.h"
#include "../sync/sync_engine.h"
#include "../utils/logger.h"
#include "../utils/system_info.h"
#include "../utils/raid_info.h"
#include "../utils/settings_manager.h"
#include "../baluhost_client.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <sstream>
#include <string>

using json = nlohmann::json;

namespace baludesk {

IpcServer::IpcServer(SyncEngine* engine) : engine_(engine) {}

IpcServer::~IpcServer() {}

bool IpcServer::start() {
    Logger::info("IPC Server started, listening on stdin");
    return true;
}

void IpcServer::stop() {
    Logger::info("IPC Server stopped");
}

void IpcServer::processMessages() {
    // Non-blocking read from stdin
    std::string line;
    if (std::getline(std::cin, line)) {
        if (line.empty()) return;
        
        try {
            // Parse JSON message
            auto message = json::parse(line);
            
            if (!message.contains("type")) {
                Logger::error("IPC message missing 'type' field");
                return;
            }
            
            std::string type = message["type"];
            Logger::debug("Received IPC message: {}", type);
            
            // Extract request ID for responses
            int requestId = message.value("id", -1);
            
            // Handle different message types
            if (type == "ping") {
                handlePing(requestId);
            }
            else if (type == "login") {
                handleLogin(message, requestId);
            }
            else if (type == "add_sync_folder") {
                handleAddSyncFolder(message, requestId);
            }
            else if (type == "remove_sync_folder") {
                handleRemoveSyncFolder(message, requestId);
            }
            else if (type == "pause_sync") {
                handlePauseSync(message, requestId);
            }
            else if (type == "resume_sync") {
                handleResumeSync(message, requestId);
            }
            else if (type == "get_sync_state") {
                handleGetSyncState(requestId);
            }
            else if (type == "get_folders") {
                handleGetFolders(requestId);
            }
            else if (type == "get_system_info") {
                handleGetSystemInfo(requestId);
            }
            else if (type == "get_raid_status") {
                handleGetRaidStatus(requestId);
            }
            else if (type == "list_files") {
                handleListFiles(message, requestId);
            }
            else if (type == "get_mountpoints") {
                handleGetMountpoints(requestId);
            }
            else if (type == "create_folder") {
                handleCreateFolder(message, requestId);
            }
            else if (type == "rename_file") {
                handleRenameFile(message, requestId);
            }
            else if (type == "move_file") {
                handleMoveFile(message, requestId);
            }
            else if (type == "delete_file") {
                handleDeleteFile(message, requestId);
            }
            else if (type == "download_file") {
                handleDownloadFile(message, requestId);
            }
            else if (type == "upload_file") {
                handleUploadFile(message, requestId);
            }
            else if (type == "get_permissions") {
                handleGetPermissions(message, requestId);
            }
            else if (type == "set_permission") {
                handleSetPermission(message, requestId);
            }
            else if (type == "remove_permission") {
                handleRemovePermission(message, requestId);
            }
            else if (type == "get_settings") {
                handleGetSettings(message, requestId);
            }
            else if (type == "update_settings") {
                handleUpdateSettings(message, requestId);
            }
            else if (type == "get_conflicts") {
                handleGetConflicts(requestId);
            }
            else if (type == "resolve_conflict") {
                handleResolveConflict(message, requestId);
            }
            else if (type == "resolve_all_conflicts") {
                handleResolveAllConflicts(message, requestId);
            }
            else if (type == "add_remote_server_profile") {
                handleAddRemoteServerProfile(message, requestId);
            }
            else if (type == "update_remote_server_profile") {
                handleUpdateRemoteServerProfile(message, requestId);
            }
            else if (type == "delete_remote_server_profile") {
                handleDeleteRemoteServerProfile(message, requestId);
            }
            else if (type == "get_remote_server_profiles") {
                handleGetRemoteServerProfiles(requestId);
            }
            else if (type == "get_remote_server_profile") {
                handleGetRemoteServerProfile(message, requestId);
            }
            else if (type == "test_server_connection") {
                handleTestServerConnection(message, requestId);
            }
            else if (type == "start_remote_server") {
                handleStartRemoteServer(message, requestId);
            }
            else if (type == "add_vpn_profile") {
                handleAddVPNProfile(message, requestId);
            }
            else if (type == "update_vpn_profile") {
                handleUpdateVPNProfile(message, requestId);
            }
            else if (type == "delete_vpn_profile") {
                handleDeleteVPNProfile(message, requestId);
            }
            else if (type == "get_vpn_profiles") {
                handleGetVPNProfiles(requestId);
            }
            else if (type == "get_vpn_profile") {
                handleGetVPNProfile(message, requestId);
            }
            else if (type == "test_vpn_connection") {
                handleTestVPNConnection(message, requestId);
            }
            else {
                Logger::warn("Unknown IPC message type: {}", type);
                sendError("Unknown command type", requestId);
            }
            
        } catch (const json::exception& e) {
            Logger::error("Failed to parse IPC message: {}", e.what());
        }
    }
}

void IpcServer::handlePing(int requestId) {
    json response = {
        {"type", "pong"},
        {"timestamp", std::time(nullptr)}
    };
    sendResponse(response, requestId);
}

void IpcServer::handleLogin(const json& message, int requestId) {
    try {
        if (!message.contains("data")) {
            sendError("Missing data", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string username = data.value("username", "");
        std::string password = data.value("password", "");
        std::string serverUrl = data.value("serverUrl", "");
        
        if (username.empty() || password.empty() || serverUrl.empty()) {
            sendError("Username, password and serverUrl required", requestId);
            return;
        }
        
        Logger::info("Login attempt: {} @ {}", username, serverUrl);
        
        // Initialize BaluHost client
        if (!baluhostClient_) {
            baluhostClient_ = std::make_unique<BaluhostClient>(serverUrl);
        }
        
        // Authenticate with BaluHost server
        bool baluhostAuth = baluhostClient_->login(username, password);
        if (!baluhostAuth) {
            sendError("BaluHost authentication failed: " + baluhostClient_->getLastError(), requestId);
            Logger::warn("BaluHost login failed for user: {}", username);
            return;
        }
        
        // Also authenticate with SyncEngine (for backward compatibility)
        bool success = engine_->login(username, password);
        
        if (success && baluhostAuth) {
            json response = {
                {"success", true},
                {"token", "authenticated"},
                {"user", {
                    {"username", username},
                    {"id", 1}
                }}
            };
            sendResponse(response, requestId);
            Logger::info("Login successful for user: {}", username);
        } else {
            sendError("Login failed: Invalid credentials or server unreachable", requestId);
            Logger::warn("Login failed for user: {}", username);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Login error: ") + e.what(), requestId);
        Logger::error("Login exception: {}", e.what());
    }
}

void IpcServer::handleAddSyncFolder(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!message.contains("payload")) {
            sendError("Missing payload", requestId);
            return;
        }

        auto payload = message["payload"];
        std::string localPath = payload.value("local_path", "");
        std::string remotePath = payload.value("remote_path", "");

        if (localPath.empty() || remotePath.empty()) {
            sendError("local_path and remote_path required", requestId);
            return;
        }

        // Add folder via sync engine
        SyncFolder folder;
        folder.id = ""; // Will be generated by engine
        folder.localPath = localPath;
        folder.remotePath = remotePath;
        folder.enabled = true;
        folder.status = SyncStatus::IDLE;

        bool success = engine_->addSyncFolder(folder);

        if (success) {
            json response = {
                {"type", "sync_folder_added"},
                {"success", true},
                {"folder_id", folder.id}
            };
            sendResponse(response, requestId);
        } else {
            sendError("Failed to add sync folder", requestId);
        }

    } catch (const std::exception& e) {
        Logger::error("handleAddSyncFolder error: {}", e.what());
        sendError(e.what(), requestId);
    }
}

void IpcServer::handleRemoveSyncFolder(const json& message, int requestId) {
    try {
        if (!message.contains("payload") || !message["payload"].contains("folder_id")) {
            sendError("Missing folder_id", requestId);
            return;
        }

        std::string folderId = message["payload"]["folder_id"];
        bool success = engine_->removeSyncFolder(folderId);

        json response = {
            {"type", "sync_folder_removed"},
            {"success", success},
            {"folder_id", folderId}
        };
        sendResponse(response, requestId);

    } catch (const std::exception& e) {
        Logger::error("handleRemoveSyncFolder error: {}", e.what());
        sendError(e.what(), requestId);
    }
}

void IpcServer::handlePauseSync(const json& message, int requestId) {
    try {
        if (!message.contains("payload") || !message["payload"].contains("folder_id")) {
            sendError("Missing folder_id", requestId);
            return;
        }

        std::string folderId = message["payload"]["folder_id"];
        engine_->pauseSync(folderId);

        json response = {
            {"type", "sync_paused"},
            {"folder_id", folderId},
            {"success", true}
        };
        sendResponse(response, requestId);

    } catch (const std::exception& e) {
        Logger::error("handlePauseSync error: {}", e.what());
        sendError(e.what(), requestId);
    }
}

void IpcServer::handleResumeSync(const json& message, int requestId) {
    try {
        if (!message.contains("payload") || !message["payload"].contains("folder_id")) {
            sendError("Missing folder_id", requestId);
            return;
        }

        std::string folderId = message["payload"]["folder_id"];
        engine_->resumeSync(folderId);

        json response = {
            {"type", "sync_resumed"},
            {"folder_id", folderId},
            {"success", true}
        };
        sendResponse(response, requestId);

    } catch (const std::exception& e) {
        Logger::error("handleResumeSync error: {}", e.what());
        sendError(e.what(), requestId);
    }
}

void IpcServer::handleUpdateSyncFolder(const json& message, int requestId) {
    try {
        if (!message.contains("payload") || !message["payload"].contains("folder_id")) {
            sendError("Missing folder_id", requestId);
            return;
        }

        std::string folderId = message["payload"]["folder_id"];
        
        // Get conflict resolution setting if provided
        std::string conflictResolution = "ask"; // Default
        if (message["payload"].contains("conflict_resolution")) {
            conflictResolution = message["payload"]["conflict_resolution"];
        }

        // Update the folder settings in the sync engine
        // This would typically store the settings in a database
        engine_->updateSyncFolderSettings(folderId, conflictResolution);

        json response = {
            {"type", "sync_folder_updated"},
            {"folder_id", folderId},
            {"conflict_resolution", conflictResolution},
            {"success", true}
        };
        sendResponse(response, requestId);

    } catch (const std::exception& e) {
        Logger::error("handleUpdateSyncFolder error: {}", e.what());
        sendError(e.what(), requestId);
    }
}

void IpcServer::handleGetSyncState(int requestId) {
    try {
        auto state = engine_->getSyncState();

        std::string status_str = "idle";
        if (state.status == SyncStatus::SYNCING) status_str = "syncing";
        else if (state.status == SyncStatus::PAUSED) status_str = "paused";
        else if (state.status == SyncStatus::SYNC_ERROR) status_str = "error";

        json response = {
            {"type", "sync_state"},
            {"status", status_str},
            {"upload_speed", state.uploadSpeed},
            {"download_speed", state.downloadSpeed},
            {"last_sync", state.lastSync}
        };
        sendResponse(response, requestId);

    } catch (const std::exception& e) {
        Logger::error("handleGetSyncState error: {}", e.what());
        sendError(e.what(), requestId);
    }
}

void IpcServer::handleGetFolders(int requestId) {
    try {
        auto folders = engine_->getSyncFolders();

        json folderArray = json::array();
        for (const auto& folder : folders) {
            std::string status_str = "idle";
            if (folder.status == SyncStatus::SYNCING) status_str = "syncing";
            else if (folder.status == SyncStatus::PAUSED) status_str = "paused";
            else if (folder.status == SyncStatus::SYNC_ERROR) status_str = "error";

            json folderJson = {
                {"id", folder.id},
                {"local_path", folder.localPath},
                {"remote_path", folder.remotePath},
                {"status", status_str},
                {"enabled", folder.enabled},
                {"size", folder.size}
            };
            folderArray.push_back(folderJson);
        }

        json response = {
            {"type", "folders_list"},
            {"folders", folderArray}
        };
        sendResponse(response, requestId);

    } catch (const std::exception& e) {
        Logger::error("handleGetFolders error: {}", e.what());
        sendError(e.what(), requestId);
    }
}

void IpcServer::sendResponse(const json& response, int requestId) {
    json output = response;
    if (requestId >= 0) {
        output["id"] = requestId;
    }
    std::cout << output.dump() << std::endl;
    std::cout.flush();
}

void IpcServer::sendError(const std::string& error, int requestId) {
    json response = {
        {"type", "error"},
        {"message", error},
        {"error", error},
        {"success", false}
    };
    if (requestId >= 0) {
        response["id"] = requestId;
    }
    std::cout << response.dump() << std::endl;
    std::cout.flush();
}

void IpcServer::broadcastEvent(const std::string& eventType, const json& data) {
    json event = {
        {"type", eventType},
        {"data", data}
    };
    sendResponse(event, -1);
}

// File operation handlers
void IpcServer::handleListFiles(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string path = data.value("path", "/");
        std::string mountId = data.value("mountId", "");
        
        auto files = baluhostClient_->listFiles(path, mountId);
        
        json filesJson = json::array();
        for (const auto& file : files) {
            filesJson.push_back({
                {"id", file.id},
                {"name", file.name},
                {"path", file.path},
                {"type", file.type},
                {"size", file.size},
                {"owner", file.owner},
                {"created_at", file.created_at},
                {"updated_at", file.updated_at}
            });
            if (file.mount_id.has_value()) {
                filesJson.back()["mount_id"] = file.mount_id.value();
            }
        }
        
        json response = {
            {"success", true},
            {"files", filesJson}
        };
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("List files error: ") + e.what(), requestId);
    }
}

void IpcServer::handleGetMountpoints(int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto mountpoints = baluhostClient_->getMountpoints();
        
        json mountpointsJson = json::array();
        for (const auto& mp : mountpoints) {
            mountpointsJson.push_back({
                {"id", mp.id},
                {"name", mp.name},
                {"mount_path", mp.mount_path},
                {"raid_level", mp.raid_level},
                {"total_size", mp.total_size},
                {"used_size", mp.used_size}
            });
        }
        
        json response = {
            {"success", true},
            {"mountpoints", mountpointsJson}
        };
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Get mountpoints error: ") + e.what(), requestId);
    }
}

void IpcServer::handleCreateFolder(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string path = data.value("path", "");
        std::string name = data.value("name", "");
        std::string mountId = data.value("mountId", "");
        
        if (name.empty()) {
            sendError("Folder name required", requestId);
            return;
        }
        
        bool success = baluhostClient_->createFolder(path, name, mountId);
        
        if (success) {
            json response = {{"success", true}};
            sendResponse(response, requestId);
        } else {
            sendError("Failed to create folder: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Create folder error: ") + e.what(), requestId);
    }
}

void IpcServer::handleRenameFile(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        int fileId = data.value("fileId", 0);
        std::string newName = data.value("newName", "");
        
        if (fileId == 0 || newName.empty()) {
            sendError("File ID and new name required", requestId);
            return;
        }
        
        bool success = baluhostClient_->renameFile(fileId, newName);
        
        if (success) {
            json response = {{"success", true}};
            sendResponse(response, requestId);
        } else {
            sendError("Failed to rename file: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Rename file error: ") + e.what(), requestId);
    }
}

void IpcServer::handleMoveFile(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        int fileId = data.value("fileId", 0);
        std::string newPath = data.value("newPath", "");
        
        if (fileId == 0 || newPath.empty()) {
            sendError("File ID and new path required", requestId);
            return;
        }
        
        bool success = baluhostClient_->moveFile(fileId, newPath);
        
        if (success) {
            json response = {{"success", true}};
            sendResponse(response, requestId);
        } else {
            sendError("Failed to move file: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Move file error: ") + e.what(), requestId);
    }
}

void IpcServer::handleDeleteFile(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        int fileId = data.value("fileId", 0);
        
        if (fileId == 0) {
            sendError("File ID required", requestId);
            return;
        }
        
        bool success = baluhostClient_->deleteFile(fileId);
        
        if (success) {
            json response = {{"success", true}};
            sendResponse(response, requestId);
        } else {
            sendError("Failed to delete file: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Delete file error: ") + e.what(), requestId);
    }
}

void IpcServer::handleDownloadFile(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string remotePath = data.value("remotePath", "");
        std::string localPath = data.value("localPath", "");
        
        if (remotePath.empty() || localPath.empty()) {
            sendError("Remote path and local path required", requestId);
            return;
        }
        
        bool success = baluhostClient_->downloadFileByPath(remotePath, localPath);
        
        if (success) {
            json response = {
                {"success", true},
                {"localPath", localPath}
            };
            sendResponse(response, requestId);
        } else {
            sendError("Failed to download file: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Download file error: ") + e.what(), requestId);
    }
}

void IpcServer::handleUploadFile(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string localPath = data.value("localPath", "");
        std::string remotePath = data.value("remotePath", "/");
        std::string mountId = data.value("mountId", "");
        
        if (localPath.empty()) {
            sendError("Local file path required", requestId);
            return;
        }
        
        bool success = baluhostClient_->uploadFile(localPath, remotePath, mountId);
        
        if (success) {
            json response = {{"success", true}};
            sendResponse(response, requestId);
        } else {
            sendError("Failed to upload file: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Upload file error: ") + e.what(), requestId);
    }
}

void IpcServer::handleGetPermissions(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        int fileId = data.value("fileId", 0);
        
        if (fileId == 0) {
            sendError("File ID required", requestId);
            return;
        }
        
        auto permissions = baluhostClient_->getPermissions(fileId);
        
        json permsJson = json::array();
        for (const auto& perm : permissions) {
            permsJson.push_back({
                {"username", perm.username},
                {"can_view", perm.can_view},
                {"can_edit", perm.can_edit},
                {"can_delete", perm.can_delete}
            });
        }
        
        json response = {
            {"success", true},
            {"permissions", permsJson}
        };
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Get permissions error: ") + e.what(), requestId);
    }
}

void IpcServer::handleSetPermission(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        int fileId = data.value("fileId", 0);
        std::string username = data.value("username", "");
        bool canView = data.value("can_view", false);
        bool canEdit = data.value("can_edit", false);
        bool canDelete = data.value("can_delete", false);
        
        if (fileId == 0 || username.empty()) {
            sendError("File ID and username required", requestId);
            return;
        }
        
        bool success = baluhostClient_->setPermission(fileId, username, canView, canEdit, canDelete);
        
        if (success) {
            json response = {{"success", true}};
            sendResponse(response, requestId);
        } else {
            sendError("Failed to set permission: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Set permission error: ") + e.what(), requestId);
    }
}

void IpcServer::handleRemovePermission(const json& message, int requestId) {
    (void)requestId;
    try {
        if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
            sendError("Not authenticated to BaluHost server", requestId);
            return;
        }
        
        auto data = message["data"];
        int fileId = data.value("fileId", 0);
        std::string username = data.value("username", "");
        
        if (fileId == 0 || username.empty()) {
            sendError("File ID and username required", requestId);
            return;
        }
        
        bool success = baluhostClient_->removePermission(fileId, username);
        
        if (success) {
            json response = {{"success", true}};
            sendResponse(response, requestId);
        } else {
            sendError("Failed to remove permission: " + baluhostClient_->getLastError(), requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Remove permission error: ") + e.what(), requestId);
    }
}

void IpcServer::handleGetSystemInfo(int requestId) {
    try {
        auto sysInfo = SystemInfoCollector::getSystemInfo();

        json response = {
            {"type", "system_info"},
            {"success", true},
            {"data", {
                {"cpu", {
                    {"usage", sysInfo.cpu.usage},
                    {"cores", sysInfo.cpu.cores},
                    {"frequency_mhz", sysInfo.cpu.frequency}
                }},
                {"memory", {
                    {"total", sysInfo.memory.total},
                    {"used", sysInfo.memory.used},
                    {"available", sysInfo.memory.available}
                }},
                {"disk", {
                    {"total", sysInfo.disk.total},
                    {"used", sysInfo.disk.used},
                    {"available", sysInfo.disk.available}
                }},
                {"uptime", sysInfo.uptime}
            }}
        };
        
        sendResponse(response, requestId);
        Logger::debug("System info sent to frontend");
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get system info: ") + e.what(), requestId);
        Logger::error("Error in handleGetSystemInfo: {}", e.what());
    }
}

void IpcServer::handleGetRaidStatus(int requestId) {
    try {
        auto raidStatus = RaidInfoCollector::getRaidStatus();

        json response = {
            {"type", "raid_status"},
            {"success", true},
            {"data", raidStatus.toJson()}
        };
        
        sendResponse(response, requestId);
        Logger::debug("RAID status sent to frontend");
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get RAID status: ") + e.what(), requestId);
        Logger::error("Error in handleGetRaidStatus: {}", e.what());
    }
}

void IpcServer::handleGetSettings(const nlohmann::json& message, int requestId) {
    try {
        auto& settingsManager = SettingsManager::getInstance();
        auto settings = settingsManager.getSettings();
        
        json response = {
            {"type", "settings_response"},
            {"success", true},
            {"data", settings}
        };
        
        // Preserve the requestId from the message
        if (message.contains("requestId")) {
            response["requestId"] = message["requestId"];
        }
        
        sendResponse(response, requestId);
        Logger::debug("Settings sent to frontend");
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get settings: ") + e.what(), requestId);
        Logger::error("Error in handleGetSettings: {}", e.what());
    }
}

void IpcServer::handleUpdateSettings(const nlohmann::json& message, int requestId) {
    try {
        if (!message.contains("data")) {
            sendError("Missing 'data' field in update_settings", requestId);
            return;
        }
        
        auto& settingsManager = SettingsManager::getInstance();
        bool success = settingsManager.updateSettings(message["data"]);
        
        json response = {
            {"type", "settings_updated"},
            {"success", success}
        };
        
        // Preserve the requestId from the message
        if (message.contains("requestId")) {
            response["requestId"] = message["requestId"];
        }
        
        if (success) {
            response["data"] = settingsManager.getSettings();
            Logger::info("Settings updated successfully");
        } else {
            response["error"] = "Failed to update settings";
        }
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to update settings: ") + e.what(), requestId);
        Logger::error("Error in handleUpdateSettings: {}", e.what());
    }
}

void IpcServer::handleGetConflicts(int requestId) {
    try {
        json response;
        response["type"] = "conflicts";
        response["success"] = true;
        response["id"] = requestId;
        
        // Mock conflicts for dev mode
        // In production, this would query actual sync engine for conflicts
        json conflicts = json::array();
        
        // Mock conflict 1: modified-modified
        json conflict1;
        conflict1["id"] = "conflict_1";
        conflict1["path"] = "/Documents/report.txt";
        conflict1["conflictType"] = "modified-modified";
        conflict1["localVersion"]["size"] = 2048;
        conflict1["localVersion"]["modifiedAt"] = "2026-01-05T16:30:00Z";
        conflict1["localVersion"]["hash"] = "abc123local";
        conflict1["localVersion"]["exists"] = true;
        conflict1["localVersion"]["content"] = "This is the local version\nwith some content...";
        conflict1["remoteVersion"]["size"] = 2150;
        conflict1["remoteVersion"]["modifiedAt"] = "2026-01-05T17:00:00Z";
        conflict1["remoteVersion"]["hash"] = "abc456remote";
        conflict1["remoteVersion"]["exists"] = true;
        conflict1["remoteVersion"]["content"] = "This is the remote version\nwith updated content...";
        conflicts.push_back(conflict1);
        
        // Mock conflict 2: deleted-modified
        json conflict2;
        conflict2["id"] = "conflict_2";
        conflict2["path"] = "/Pictures/vacation.jpg";
        conflict2["conflictType"] = "modified-deleted";
        conflict2["localVersion"]["size"] = 0;
        conflict2["localVersion"]["modifiedAt"] = "2026-01-05T15:00:00Z";
        conflict2["localVersion"]["hash"] = "";
        conflict2["localVersion"]["exists"] = false;
        conflict2["remoteVersion"]["size"] = 1024000;
        conflict2["remoteVersion"]["modifiedAt"] = "2026-01-05T14:00:00Z";
        conflict2["remoteVersion"]["hash"] = "def789remote";
        conflict2["remoteVersion"]["exists"] = true;
        conflicts.push_back(conflict2);
        
        response["data"]["conflicts"] = conflicts;
        Logger::info("Returning {} conflicts", conflicts.size());
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get conflicts: ") + e.what(), requestId);
        Logger::error("Error in handleGetConflicts: {}", e.what());
    }
}

void IpcServer::handleResolveConflict(const json& message, int requestId) {
    try {
        if (!message.contains("data")) {
            sendError("Missing 'data' field in resolve_conflict message", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string conflictId = data.value("conflictId", "");
        std::string resolution = data.value("resolution", "");
        
        if (conflictId.empty() || resolution.empty()) {
            sendError("Missing conflictId or resolution", requestId);
            return;
        }
        
        Logger::info("Resolving conflict {} with strategy: {}", conflictId, resolution);
        
        // In production: apply resolution strategy to sync engine
        // resolution: "keep-local" | "keep-remote" | "keep-both" | "manual"
        
        json response;
        response["type"] = "conflict_resolved";
        response["success"] = true;
        response["id"] = requestId;
        response["data"]["conflictId"] = conflictId;
        response["data"]["resolution"] = resolution;
        response["data"]["message"] = "Conflict resolved successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to resolve conflict: ") + e.what(), requestId);
        Logger::error("Error in handleResolveConflict: {}", e.what());
    }
}

void IpcServer::handleResolveAllConflicts(const json& message, int requestId) {
    try {
        if (!message.contains("data")) {
            sendError("Missing 'data' field in resolve_all_conflicts message", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string resolution = data.value("resolution", "");
        
        if (resolution.empty()) {
            sendError("Missing resolution strategy", requestId);
            return;
        }
        
        Logger::info("Resolving all conflicts with strategy: {}", resolution);
        
        // In production: apply bulk resolution to all conflicts
        
        json response;
        response["type"] = "all_conflicts_resolved";
        response["success"] = true;
        response["id"] = requestId;
        response["data"]["resolution"] = resolution;
        response["data"]["resolvedCount"] = 2;  // Mock: resolved 2 conflicts
        response["data"]["message"] = "All conflicts resolved successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to resolve conflicts: ") + e.what(), requestId);
        Logger::error("Error in handleResolveAllConflicts: {}", e.what());
    }
}

// ============================================================================
// Remote Server Profile Handlers
// ============================================================================

void IpcServer::handleAddRemoteServerProfile(const json& message, int requestId) {
    try {
        RemoteServerProfile profile;
        profile.name = message["name"];
        profile.sshHost = message["sshHost"];
        profile.sshPort = message.value("sshPort", 22);
        profile.sshUsername = message["sshUsername"];
        profile.sshPrivateKey = message["sshPrivateKey"];
        profile.vpnProfileId = message.value("vpnProfileId", 0);
        profile.powerOnCommand = message.value("powerOnCommand", "");
        
        // TODO: Add to database via engine
        json response = json::object();
        response["type"] = "add_remote_server_profile_response";
        response["success"] = true;
        response["data"]["id"] = 1;  // Mock ID
        response["data"]["message"] = "Remote server profile added successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to add remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleAddRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleUpdateRemoteServerProfile(const json& message, int requestId) {
    try {
        int id = message["id"];
        RemoteServerProfile profile;
        profile.id = id;
        profile.name = message["name"];
        profile.sshHost = message["sshHost"];
        profile.sshPort = message.value("sshPort", 22);
        profile.sshUsername = message["sshUsername"];
        profile.sshPrivateKey = message["sshPrivateKey"];
        profile.vpnProfileId = message.value("vpnProfileId", 0);
        profile.powerOnCommand = message.value("powerOnCommand", "");
        
        // TODO: Update in database via engine
        json response = json::object();
        response["type"] = "update_remote_server_profile_response";
        response["success"] = true;
        response["data"]["message"] = "Remote server profile updated successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to update remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleUpdateRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleDeleteRemoteServerProfile(const json& message, int requestId) {
    try {
        int id = message["id"];
        
        // TODO: Delete from database via engine
        json response = json::object();
        response["type"] = "delete_remote_server_profile_response";
        response["success"] = true;
        response["data"]["message"] = "Remote server profile deleted successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to delete remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleDeleteRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleGetRemoteServerProfiles(int requestId) {
    try {
        // TODO: Get from database via engine
        json response = json::object();
        response["type"] = "get_remote_server_profiles_response";
        response["success"] = true;
        response["data"]["profiles"] = json::array();
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get remote server profiles: ") + e.what(), requestId);
        Logger::error("Error in handleGetRemoteServerProfiles: {}", e.what());
    }
}

void IpcServer::handleGetRemoteServerProfile(const json& message, int requestId) {
    try {
        int id = message["id"];
        
        // TODO: Get from database via engine
        json response = json::object();
        response["type"] = "get_remote_server_profile_response";
        response["success"] = true;
        response["data"]["profile"] = json::object();
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleGetRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleTestServerConnection(const json& message, int requestId) {
    try {
        int id = message["id"];
        
        // TODO: Test SSH connection
        json response = json::object();
        response["type"] = "test_server_connection_response";
        response["success"] = true;
        response["data"]["connected"] = true;
        response["data"]["message"] = "Connection successful";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to test server connection: ") + e.what(), requestId);
        Logger::error("Error in handleTestServerConnection: {}", e.what());
    }
}

void IpcServer::handleStartRemoteServer(const json& message, int requestId) {
    try {
        int id = message["id"];
        
        // TODO: Execute SSH command to start server
        json response = json::object();
        response["type"] = "start_remote_server_response";
        response["success"] = true;
        response["data"]["message"] = "Server start command sent";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to start remote server: ") + e.what(), requestId);
        Logger::error("Error in handleStartRemoteServer: {}", e.what());
    }
}

// ============================================================================
// VPN Profile Handlers
// ============================================================================

void IpcServer::handleAddVPNProfile(const json& message, int requestId) {
    try {
        VPNProfile profile;
        profile.name = message["name"];
        profile.vpnType = message["vpnType"];
        profile.description = message.value("description", "");
        profile.configContent = message["configContent"];
        profile.certificate = message.value("certificate", "");
        profile.privateKey = message.value("privateKey", "");
        profile.autoConnect = message.value("autoConnect", false);
        
        // TODO: Add to database via engine
        json response = json::object();
        response["type"] = "add_vpn_profile_response";
        response["success"] = true;
        response["data"]["id"] = 1;  // Mock ID
        response["data"]["message"] = "VPN profile added successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to add VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleAddVPNProfile: {}", e.what());
    }
}

void IpcServer::handleUpdateVPNProfile(const json& message, int requestId) {
    try {
        int id = message["id"];
        VPNProfile profile;
        profile.id = id;
        profile.name = message["name"];
        profile.vpnType = message["vpnType"];
        profile.description = message.value("description", "");
        profile.configContent = message["configContent"];
        profile.certificate = message.value("certificate", "");
        profile.privateKey = message.value("privateKey", "");
        profile.autoConnect = message.value("autoConnect", false);
        
        // TODO: Update in database via engine
        json response = json::object();
        response["type"] = "update_vpn_profile_response";
        response["success"] = true;
        response["data"]["message"] = "VPN profile updated successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to update VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleUpdateVPNProfile: {}", e.what());
    }
}

void IpcServer::handleDeleteVPNProfile(const json& message, int requestId) {
    try {
        int id = message["id"];
        
        // TODO: Delete from database via engine
        json response = json::object();
        response["type"] = "delete_vpn_profile_response";
        response["success"] = true;
        response["data"]["message"] = "VPN profile deleted successfully";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to delete VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleDeleteVPNProfile: {}", e.what());
    }
}

void IpcServer::handleGetVPNProfiles(int requestId) {
    try {
        // TODO: Get from database via engine
        json response = json::object();
        response["type"] = "get_vpn_profiles_response";
        response["success"] = true;
        response["data"]["profiles"] = json::array();
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get VPN profiles: ") + e.what(), requestId);
        Logger::error("Error in handleGetVPNProfiles: {}", e.what());
    }
}

void IpcServer::handleGetVPNProfile(const json& message, int requestId) {
    try {
        int id = message["id"];
        
        // TODO: Get from database via engine
        json response = json::object();
        response["type"] = "get_vpn_profile_response";
        response["success"] = true;
        response["data"]["profile"] = json::object();
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleGetVPNProfile: {}", e.what());
    }
}

void IpcServer::handleTestVPNConnection(const json& message, int requestId) {
    try {
        int id = message["id"];
        
        // TODO: Test VPN connection
        json response = json::object();
        response["type"] = "test_vpn_connection_response";
        response["success"] = true;
        response["data"]["connected"] = true;
        response["data"]["message"] = "VPN connection test successful";
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to test VPN connection: ") + e.what(), requestId);
        Logger::error("Error in handleTestVPNConnection: {}", e.what());
    }
}

}  // namespace baludesk

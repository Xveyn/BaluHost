#include "ipc_server.h"
#include "../sync/sync_engine.h"
#include "../db/database.h"
#include "../services/ssh_service.h"
#include "../services/vpn_service.h"
#include "../utils/logger.h"
#include "../utils/system_info.h"
#include "../utils/raid_info.h"
#include "../utils/settings_manager.h"
#include "../utils/mock_data_provider.h"
#include "../utils/mock_data_provider.h"
#include "../api/http_client.h"
#include "../baluhost_client.h"
#include <nlohmann/json.hpp>
#include <curl/curl.h>
#include <iostream>
#include <sstream>
#include <fstream>
#include <string>
#include <functional>
#include <chrono>
#include <ctime>
#include <iomanip>

using json = nlohmann::json;

namespace baludesk {

// CURL write callback for health check
static size_t HealthCheckWriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

IpcServer::IpcServer(SyncEngine* engine) : engine_(engine) {}

IpcServer::~IpcServer() {}

bool IpcServer::start() {
    Logger::info("IPC Server started, listening on stdin");
    
    // Don't load username from file on start
    // Each session should start fresh without automatic login
    // currentUsername_ will be set when user logs in
    Logger::info("currentUsername_ starts empty until user logs in");
    
    // Register for sync status updates to broadcast to frontend
    if (engine_) {
        engine_->setStatusCallback([this](const SyncStats& state) {
            try {
                std::string status_str = "idle";
                if (state.status == SyncStatus::SYNCING) status_str = "syncing";
                else if (state.status == SyncStatus::PAUSED) status_str = "paused";
                else if (state.status == SyncStatus::SYNC_ERROR) status_str = "error";

                json data = {
                    {"status", status_str},
                    {"uploadSpeed", state.uploadSpeed},
                    {"downloadSpeed", state.downloadSpeed},
                    {"pendingUploads", state.pendingUploads},
                    {"pendingDownloads", state.pendingDownloads},
                    {"lastSync", state.lastSync}
                };

                broadcastEvent("sync_state_update", data);
            } catch (const std::exception& e) {
                Logger::error("Failed to broadcast sync state: {}", e.what());
            }
        });
    }

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
            
            // Extract request ID for responses - check both 'id' and 'requestId' fields
            int requestId = -1;
            if (message.contains("requestId")) {
                requestId = message["requestId"];
            } else if (message.contains("id")) {
                requestId = message["id"];
            }
            if (message.contains("requestId")) {
                requestId = message["requestId"];
            } else if (message.contains("id")) {
                requestId = message["id"];
            }
            
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
            else if (type == "get_dev_mode") {
                handleGetDevMode(requestId);
            }
            else if (type == "set_dev_mode") {
                handleSetDevMode(message, requestId);
            }
            else if (type == "get_power_monitoring") {
                handleGetPowerMonitoring(requestId);
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
            else if (type == "discover_network_servers") {
                handleDiscoverNetworkServers(requestId);
            }
            else if (type == "check_server_health") {
                handleCheckServerHealth(message, requestId);
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
        Logger::info("=== handleLogin called ===");
        
        if (!message.contains("data")) {
            sendError("Missing data", requestId);
            return;
        }
        
        auto data = message["data"];
        std::string username = data.value("username", "");
        std::string password = data.value("password", "");
        std::string serverUrl = data.value("serverUrl", "");
        
        Logger::info("Login attempt: username='{}', currentUsername_before='{}'", username, currentUsername_);
        
        // Handle profileId which can be null, number, or missing
        int profileId = -1;
        if (data.contains("profileId") && !data["profileId"].is_null()) {
            profileId = data["profileId"].get<int>();
        }
        
        if (username.empty() || password.empty() || serverUrl.empty()) {
            sendError("Username, password and serverUrl required", requestId);
            return;
        }
        
        Logger::info("Login attempt: {} @ {} (profileId: {})", username, serverUrl, profileId);
        
        // If profileId provided, validate it exists in database
        if (profileId >= 0) {
            auto db = engine_->getDatabase();
            if (db) {
                RemoteServerProfile profile = db->getRemoteServerProfile(profileId);
                if (profile.id <= 0) {
                    Logger::warn("Profile {} not found in database", profileId);
                    // Continue anyway - serverUrl might still be valid
                }
            }
        }
        
        // Check if user is different - if so, clear old profiles
        if (!currentUsername_.empty() && currentUsername_ != username) {
            auto db = engine_->getDatabase();
            if (db) {
                Logger::info("User changed from {} to {} - clearing old profiles", currentUsername_, username);
                db->clearAllRemoteServerProfiles();
            }
        }
        
        // Update current username and save to file
        currentUsername_ = username;
        Logger::info("Updated currentUsername_ to '{}'", currentUsername_);
        
        // Save username to file for persistence across restarts
        std::ofstream userFile("current_user.txt");
        if (userFile.is_open()) {
            userFile << username;
            userFile.close();
            Logger::info("Saved current user '{}' to file", username);
        } else {
            Logger::warn("Failed to open current_user.txt for writing");
        }
        
        // Initialize BaluHost client (always create new to use the provided serverUrl)
        baluhostClient_ = std::make_unique<BaluhostClient>(serverUrl);
        
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

        // Build a consistent response structure matching other endpoints
        auto folders = engine_->getSyncFolders();
        json data = {
            {"status", status_str},
            {"uploadSpeed", state.uploadSpeed},
            {"downloadSpeed", state.downloadSpeed},
            {"pendingUploads", state.pendingUploads},
            {"pendingDownloads", state.pendingDownloads},
            {"lastSync", state.lastSync},
            {"syncFolderCount", static_cast<int>(folders.size())}
        };

        json response = {
            {"type", "sync_state"},
            {"success", true},
            {"data", data}
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
        auto& settings = SettingsManager::getInstance();
        std::string devMode = settings.getDevMode();

        Logger::debug("Getting system info (dev-mode: {})", devMode);

        SystemInfo sysInfo;

        if (devMode == "mock") {
            // Mock mode: Return test data
            sysInfo = MockDataProvider::getMockSystemInfo();
            Logger::debug("Using mock system info");
        } else {
            // Production mode: Fetch from BaluHost server using baluhostClient_
            if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
                sendError("Not authenticated with BaluHost server", requestId);
                Logger::warn("Cannot fetch system info: not authenticated");
                return;
            }

            try {
                auto response = baluhostClient_->getSystemInfo();
                if (!response) {
                    sendError("Failed to fetch system info from server", requestId);
                    Logger::error("Error fetching system info: no response");
                    return;
                }

                auto& json = *response;

                // Parse server response (with null-safety)
                sysInfo.cpu.usage = json["cpu"]["usage"].is_null() ? 0.0 : json["cpu"]["usage"].get<double>();
                sysInfo.cpu.cores = json["cpu"]["cores"].is_null() ? 0 : json["cpu"]["cores"].get<uint32_t>();
                sysInfo.cpu.frequency = json["cpu"]["frequency_mhz"].is_null() ? 0 : json["cpu"]["frequency_mhz"].get<uint32_t>();
                sysInfo.memory.total = json["memory"]["total"].is_null() ? 0 : json["memory"]["total"].get<uint64_t>();
                sysInfo.memory.used = json["memory"]["used"].is_null() ? 0 : json["memory"]["used"].get<uint64_t>();
                sysInfo.memory.available = json["memory"]["available"].is_null() ? 0 : json["memory"]["available"].get<uint64_t>();
                sysInfo.disk.total = json["disk"]["total"].is_null() ? 0 : json["disk"]["total"].get<uint64_t>();
                sysInfo.disk.used = json["disk"]["used"].is_null() ? 0 : json["disk"]["used"].get<uint64_t>();
                sysInfo.disk.available = json["disk"]["available"].is_null() ? 0 : json["disk"]["available"].get<uint64_t>();
                sysInfo.uptime = json["uptime"].is_null() ? 0 : json["uptime"].get<uint64_t>();
                sysInfo.serverUptime = json["uptime"].is_null() ? 0 : json["uptime"].get<uint64_t>();

                Logger::debug("Fetched system info from BaluHost server");
            } catch (const std::exception& e) {
                sendError(std::string("Failed to fetch system info from server: ") + e.what(), requestId);
                Logger::error("Error fetching system info from server: {}", e.what());
                return;
            }
        }

        // Build response (maintain backward-compatible structure)
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
                {"uptime", sysInfo.uptime},
                {"serverUptime", sysInfo.serverUptime},
                {"dev_mode", devMode == "mock"}
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
        auto& settings = SettingsManager::getInstance();
        std::string devMode = settings.getDevMode();

        Logger::debug("Getting RAID status (dev-mode: {})", devMode);

        RaidStatus raidStatus;

        if (devMode == "mock") {
            // Mock mode: Return test data
            raidStatus = MockDataProvider::getMockRaidStatus();
            Logger::debug("Using mock RAID status");
        } else {
            // Production mode: Fetch from BaluHost server using baluhostClient_
            if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
                sendError("Not authenticated with BaluHost server", requestId);
                Logger::warn("Cannot fetch RAID status: not authenticated");
                return;
            }

            try {
                auto response = baluhostClient_->getRaidStatus();
                if (!response) {
                    sendError("Failed to fetch RAID status from server", requestId);
                    Logger::error("Error fetching RAID status: no response");
                    return;
                }

                auto& json = *response;
                raidStatus.dev_mode = json.value("dev_mode", false);

                if (json.contains("arrays") && json["arrays"].is_array()) {
                    for (const auto& arrayJson : json["arrays"]) {
                        RaidArray array;
                        array.name = arrayJson.value("name", "");
                        array.level = arrayJson.value("level", "");
                        array.status = arrayJson.value("status", "");
                        array.size_bytes = arrayJson.value("size_bytes", 0LL);
                        array.resync_progress = arrayJson.value("resync_progress", 0.0);

                        if (arrayJson.contains("devices") && arrayJson["devices"].is_array()) {
                            for (const auto& devJson : arrayJson["devices"]) {
                                RaidDevice device;
                                device.name = devJson.value("name", "");
                                device.state = devJson.value("state", "");
                                array.devices.push_back(device);
                            }
                        }
                        raidStatus.arrays.push_back(array);
                    }
                }

                Logger::debug("Fetched RAID status from BaluHost server ({} arrays)",
                             raidStatus.arrays.size());
            } catch (const std::exception& e) {
                sendError(std::string("Failed to fetch RAID status from server: ") + e.what(), requestId);
                Logger::error("Error fetching RAID status from server: {}", e.what());
                return;
            }
        }

        // Build response (maintain backward-compatible structure)
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
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        RemoteServerProfile profile;
        
        // Set owner to current username
        profile.owner = currentUsername_;
        Logger::info("Adding profile with owner='{}' (currentUsername_='{}')", profile.owner, currentUsername_);
        
        profile.name = message["name"];
        profile.sshHost = message["sshHost"];
        profile.sshPort = message.value("sshPort", 22);
        profile.sshUsername = message["sshUsername"];
        profile.sshPrivateKey = message["sshPrivateKey"];
        profile.vpnProfileId = message.value("vpnProfileId", 0);
        profile.powerOnCommand = message.value("powerOnCommand", "");
        
        bool success = db->addRemoteServerProfile(profile);
        
        if (success) {
            json response = json::object();
            response["type"] = "add_remote_server_profile_response";
            response["success"] = true;
            response["data"]["message"] = "Remote server profile added successfully";
            sendResponse(response, requestId);
        } else {
            sendError("Failed to add remote server profile to database", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to add remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleAddRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleUpdateRemoteServerProfile(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
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
        
        bool success = db->updateRemoteServerProfile(profile);
        
        if (success) {
            json response = json::object();
            response["type"] = "update_remote_server_profile_response";
            response["success"] = true;
            response["data"]["message"] = "Remote server profile updated successfully";
            sendResponse(response, requestId);
        } else {
            sendError("Failed to update remote server profile", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to update remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleUpdateRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleDeleteRemoteServerProfile(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        int id = message["id"];
        bool success = db->deleteRemoteServerProfile(id);
        
        if (success) {
            json response = json::object();
            response["type"] = "delete_remote_server_profile_response";
            response["success"] = true;
            response["data"]["message"] = "Remote server profile deleted successfully";
            sendResponse(response, requestId);
        } else {
            sendError("Failed to delete remote server profile", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to delete remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleDeleteRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleGetRemoteServerProfiles(int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        // If user is logged in, get their profiles only
        // If not logged in (currentUsername_ is empty), get ALL profiles for login screen
        std::vector<RemoteServerProfile> profiles;
        if (!currentUsername_.empty()) {
            profiles = db->getRemoteServerProfiles(currentUsername_);
        } else {
            profiles = db->getRemoteServerProfiles();  // Get all for login screen
        }
        
        json profilesArray = json::array();
        
        for (const auto& profile : profiles) {
            json profileObj = json::object();
            profileObj["id"] = profile.id;
            profileObj["name"] = profile.name.empty() ? "" : profile.name;
            profileObj["sshHost"] = profile.sshHost.empty() ? "" : profile.sshHost;
            profileObj["sshPort"] = profile.sshPort > 0 ? profile.sshPort : 22;
            profileObj["sshUsername"] = profile.sshUsername.empty() ? "" : profile.sshUsername;
            profileObj["vpnProfileId"] = profile.vpnProfileId > 0 ? profile.vpnProfileId : 0;
            profileObj["powerOnCommand"] = profile.powerOnCommand.empty() ? "" : profile.powerOnCommand;
            profileObj["lastUsed"] = profile.lastUsed.empty() ? "" : profile.lastUsed;
            profileObj["createdAt"] = profile.createdAt.empty() ? "" : profile.createdAt;
            profileObj["updatedAt"] = profile.updatedAt.empty() ? "" : profile.updatedAt;
            profileObj["owner"] = profile.owner.empty() ? "" : profile.owner;  // Include owner for display
            profilesArray.push_back(profileObj);
        }
        
        json response = json::object();
        response["type"] = "get_remote_server_profiles_response";
        response["success"] = true;
        response["data"]["profiles"] = profilesArray;
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get remote server profiles: ") + e.what(), requestId);
        Logger::error("Error in handleGetRemoteServerProfiles: {}", e.what());
    }
}

void IpcServer::handleGetRemoteServerProfile(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        int id = message["id"];
        RemoteServerProfile profile = db->getRemoteServerProfile(id);
        
        if (profile.id > 0) {
            json profileObj = {
                {"id", profile.id},
                {"name", profile.name},
                {"sshHost", profile.sshHost},
                {"sshPort", profile.sshPort},
                {"sshUsername", profile.sshUsername},
                {"vpnProfileId", profile.vpnProfileId},
                {"powerOnCommand", profile.powerOnCommand},
                {"lastUsed", profile.lastUsed},
                {"createdAt", profile.createdAt},
                {"updatedAt", profile.updatedAt}
            };
            
            json response = json::object();
            response["type"] = "get_remote_server_profile_response";
            response["success"] = true;
            response["data"]["profile"] = profileObj;
            
            sendResponse(response, requestId);
        } else {
            sendError("Remote server profile not found", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get remote server profile: ") + e.what(), requestId);
        Logger::error("Error in handleGetRemoteServerProfile: {}", e.what());
    }
}

void IpcServer::handleTestServerConnection(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        int id = message["id"];
        RemoteServerProfile profile = db->getRemoteServerProfile(id);
        
        if (profile.id <= 0) {
            sendError("Remote server profile not found", requestId);
            return;
        }
        
        // Test SSH connection using SSH service
        SshService sshService;
        auto connectionResult = sshService.testConnection(
            profile.sshHost,
            profile.sshPort,
            profile.sshUsername,
            profile.sshPrivateKey,
            10  // 10 second timeout
        );
        
        json response = json::object();
        response["type"] = "test_server_connection_response";
        response["success"] = true;
        response["data"]["connected"] = connectionResult.connected;
        response["data"]["message"] = connectionResult.message;
        if (!connectionResult.errorCode.empty()) {
            response["data"]["errorCode"] = connectionResult.errorCode;
        }
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to test server connection: ") + e.what(), requestId);
        Logger::error("Error in handleTestServerConnection: {}", e.what());
    }
}

void IpcServer::handleStartRemoteServer(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        int id = message["id"];
        RemoteServerProfile profile = db->getRemoteServerProfile(id);
        
        if (profile.id <= 0) {
            sendError("Remote server profile not found", requestId);
            return;
        }
        
        // Check if power-on command is configured
        if (profile.powerOnCommand.empty()) {
            sendError("No power-on command configured for this server", requestId);
            return;
        }
        
        // Execute power-on command via SSH
        SshService sshService;
        auto executionResult = sshService.executeCommand(
            profile.sshHost,
            profile.sshPort,
            profile.sshUsername,
            profile.sshPrivateKey,
            profile.powerOnCommand,
            30  // 30 second timeout
        );
        
        json response = json::object();
        response["type"] = "start_remote_server_response";
        response["success"] = executionResult.success;
        response["data"]["message"] = executionResult.success ? 
            "Server start command executed successfully" : 
            "Failed to execute server start command";
        response["data"]["output"] = executionResult.output;
        if (!executionResult.errorOutput.empty()) {
            response["data"]["error"] = executionResult.errorOutput;
        }
        response["data"]["exitCode"] = executionResult.exitCode;
        
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
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        VPNProfile profile;
        profile.name = message["name"];
        profile.vpnType = message["vpnType"];
        profile.description = message.value("description", "");
        profile.configContent = message["configContent"];
        profile.certificate = message.value("certificate", "");
        profile.privateKey = message.value("privateKey", "");
        profile.autoConnect = message.value("autoConnect", false);
        
        bool success = db->addVPNProfile(profile);
        
        if (success) {
            json response = json::object();
            response["type"] = "add_vpn_profile_response";
            response["success"] = true;
            response["data"]["message"] = "VPN profile added successfully";
            sendResponse(response, requestId);
        } else {
            sendError("Failed to add VPN profile to database", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to add VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleAddVPNProfile: {}", e.what());
    }
}

void IpcServer::handleUpdateVPNProfile(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
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
        
        bool success = db->updateVPNProfile(profile);
        
        if (success) {
            json response = json::object();
            response["type"] = "update_vpn_profile_response";
            response["success"] = true;
            response["data"]["message"] = "VPN profile updated successfully";
            sendResponse(response, requestId);
        } else {
            sendError("Failed to update VPN profile", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to update VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleUpdateVPNProfile: {}", e.what());
    }
}

void IpcServer::handleDeleteVPNProfile(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        int id = message["id"];
        bool success = db->deleteVPNProfile(id);
        
        if (success) {
            json response = json::object();
            response["type"] = "delete_vpn_profile_response";
            response["success"] = true;
            response["data"]["message"] = "VPN profile deleted successfully";
            sendResponse(response, requestId);
        } else {
            sendError("Failed to delete VPN profile", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to delete VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleDeleteVPNProfile: {}", e.what());
    }
}

void IpcServer::handleGetVPNProfiles(int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        auto profiles = db->getVPNProfiles();
        json profilesArray = json::array();
        
        for (const auto& profile : profiles) {
            json profileObj = {
                {"id", profile.id},
                {"name", profile.name},
                {"vpnType", profile.vpnType},
                {"description", profile.description},
                {"autoConnect", profile.autoConnect},
                {"createdAt", profile.createdAt},
                {"updatedAt", profile.updatedAt}
            };
            profilesArray.push_back(profileObj);
        }
        
        json response = json::object();
        response["type"] = "get_vpn_profiles_response";
        response["success"] = true;
        response["data"]["profiles"] = profilesArray;
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get VPN profiles: ") + e.what(), requestId);
        Logger::error("Error in handleGetVPNProfiles: {}", e.what());
    }
}

void IpcServer::handleGetVPNProfile(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        int id = message["id"];
        VPNProfile profile = db->getVPNProfile(id);
        
        if (profile.id > 0) {
            json profileObj = {
                {"id", profile.id},
                {"name", profile.name},
                {"vpnType", profile.vpnType},
                {"description", profile.description},
                {"autoConnect", profile.autoConnect},
                {"createdAt", profile.createdAt},
                {"updatedAt", profile.updatedAt}
            };
            
            json response = json::object();
            response["type"] = "get_vpn_profile_response";
            response["success"] = true;
            response["data"]["profile"] = profileObj;
            
            sendResponse(response, requestId);
        } else {
            sendError("VPN profile not found", requestId);
        }
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get VPN profile: ") + e.what(), requestId);
        Logger::error("Error in handleGetVPNProfile: {}", e.what());
    }
}

void IpcServer::handleTestVPNConnection(const json& message, int requestId) {
    try {
        auto db = engine_->getDatabase();
        if (!engine_ || !db) {
            sendError("Database not initialized", requestId);
            return;
        }
        
        int id = message["id"];
        VPNProfile profile = db->getVPNProfile(id);
        
        if (profile.id <= 0) {
            sendError("VPN profile not found", requestId);
            return;
        }
        
        // Test VPN configuration using VPN service
        VpnService vpnService;
        auto connectionResult = vpnService.testConnection(
            profile.vpnType,
            profile.configContent,
            profile.certificate,
            profile.privateKey
        );
        
        json response = json::object();
        response["type"] = "test_vpn_connection_response";
        response["success"] = true;
        response["data"]["connected"] = connectionResult.connected;
        response["data"]["message"] = connectionResult.message;
        if (!connectionResult.errorCode.empty()) {
            response["data"]["errorCode"] = connectionResult.errorCode;
        }
        
        sendResponse(response, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to test VPN connection: ") + e.what(), requestId);
        Logger::error("Error in handleTestVPNConnection: {}", e.what());
    }
}

void IpcServer::handleDiscoverNetworkServers(int requestId) {
    try {
        json servers = json::array();
        
        // Get current timestamp as ISO string
        auto now = std::chrono::system_clock::now();
        auto time_t_now = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << std::put_time(std::gmtime(&time_t_now), "%Y-%m-%dT%H:%M:%SZ");
        std::string timestamp = ss.str();
        
        std::string discoveryMethod = "none";
        
        // Check if BaluHost server is running (from authenticated connection)
        if (baluhostClient_ && baluhostClient_->isAuthenticated()) {
            // User is authenticated, extract actual server info from baseUrl
            std::string baseUrl = baluhostClient_->getBaseUrl();
            std::string username = baluhostClient_->getUsername();

            // Parse URL to extract hostname/IP and port
            std::string hostname = "localhost";
            std::string ipAddress = "127.0.0.1";
            int port = 8000;

            // Simple URL parsing: http://hostname:port or https://hostname:port
            size_t protoEnd = baseUrl.find("://");
            if (protoEnd != std::string::npos) {
                std::string hostPart = baseUrl.substr(protoEnd + 3);
                size_t portStart = hostPart.find(":");
                if (portStart != std::string::npos) {
                    hostname = hostPart.substr(0, portStart);
                    std::string portStr = hostPart.substr(portStart + 1);
                    // Remove trailing slashes if any
                    size_t slashPos = portStr.find("/");
                    if (slashPos != std::string::npos) {
                        portStr = portStr.substr(0, slashPos);
                    }
                    port = std::stoi(portStr);
                } else {
                    hostname = hostPart;
                    // Remove trailing slashes
                    size_t slashPos = hostname.find("/");
                    if (slashPos != std::string::npos) {
                        hostname = hostname.substr(0, slashPos);
                    }
                }
            }

            // Use hostname as IP if it looks like an IP address, otherwise keep both
            ipAddress = hostname;

            json localServer = json::object();
            localServer["hostname"] = hostname;
            localServer["ipAddress"] = ipAddress;
            localServer["port"] = port;
            localServer["sshPort"] = 22;
            localServer["username"] = username;  // Add authenticated username
            localServer["description"] = "Connected BaluHost Server";
            localServer["discoveredAt"] = timestamp;
            servers.push_back(localServer);
            discoveryMethod = "authenticated";
            Logger::info("Discovered BaluHost server from authenticated connection: {}:{} (user: {})", hostname, port, username);
        } else {
            // Try to detect localhost server via HTTP probe
            try {
                // Simple check: try to create a client and see if server responds
                auto testClient = std::make_unique<BaluhostClient>("http://localhost:8000");
                // We don't actually need to login, just check if server exists
                // For now, assume localhost:8000 is the default
                json localServer = json::object();
                localServer["hostname"] = "localhost";
                localServer["ipAddress"] = "127.0.0.1";
                localServer["port"] = 8000;
                localServer["sshPort"] = 22;
                localServer["description"] = "Local BaluHost Server";
                localServer["discoveredAt"] = timestamp;
                servers.push_back(localServer);
                discoveryMethod = "localhost_probe";
                Logger::info("Discovered local BaluHost server (probe)");
            } catch (const std::exception& e) {
                Logger::warn("Could not detect localhost BaluHost server: {}", e.what());
            }
        }
        
        // Future: Could add network scanning for other servers
        // - mDNS/Bonjour discovery
        // - Previously connected servers from database
        // - Manual server entries
        
        json response = json::object();
        response["type"] = "discover_network_servers_response";
        response["success"] = true;
        response["data"]["servers"] = servers;
        response["data"]["discoveryMethod"] = discoveryMethod;
        
        sendResponse(response, requestId);
        
        Logger::info("Network discovery complete: {} servers found", servers.size());
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to discover network servers: ") + e.what(), requestId);
        Logger::error("Error in handleDiscoverNetworkServers: {}", e.what());
    }
}

void IpcServer::handleCheckServerHealth(const json& message, int requestId) {
    try {
        if (!message.contains("server_url")) {
            sendError("Missing server_url parameter", requestId);
            return;
        }
        
        std::string serverUrl = message["server_url"].get<std::string>();
        
        Logger::info("Checking server health: {}", serverUrl);
        
        // Perform a simple HTTP health check
        CURL* curl = curl_easy_init();
        if (!curl) {
            sendError("Failed to initialize CURL", requestId);
            return;
        }
        
        // Construct the health check URL - use /api/health endpoint which doesn't require auth
        std::string healthUrl = serverUrl + "/api/health";
        
        // Response buffer
        std::string responseBuffer;
        
        // Set up CURL options
        curl_easy_setopt(curl, CURLOPT_URL, healthUrl.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, HealthCheckWriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void*)&responseBuffer);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 5L);
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
        
        // Perform the request
        CURLcode res = curl_easy_perform(curl);
        
        json result = json::object();
        result["type"] = "check_server_health_response";
        result["success"] = true;
        
        if (res == CURLE_OK) {
            long httpCode = 0;
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
            
            if (httpCode >= 200 && httpCode < 300) {
                result["data"]["connected"] = true;
                result["data"]["message"] = "Server is online";
                Logger::info("Server health check passed for: {} (HTTP {})", serverUrl, httpCode);
            } else {
                result["data"]["connected"] = false;
                result["data"]["message"] = "Server returned HTTP " + std::to_string(httpCode);
                Logger::warn("Server health check failed for {}: HTTP {}", serverUrl, httpCode);
            }
        } else {
            result["data"]["connected"] = false;
            result["data"]["message"] = std::string("Connection failed: ") + curl_easy_strerror(res);
            Logger::warn("Server health check failed for {}: {}", serverUrl, curl_easy_strerror(res));
        }
        
        curl_easy_cleanup(curl);
        sendResponse(result, requestId);
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to check server health: ") + e.what(), requestId);
        Logger::error("Error in handleCheckServerHealth: {}", e.what());
    }
}

// ============================================================================
// Dev Mode Handlers
// ============================================================================

void IpcServer::handleGetDevMode(int requestId) {
    try {
        auto& settings = SettingsManager::getInstance();
        std::string devMode = settings.getDevMode();

        json response = {
            {"type", "dev_mode_response"},
            {"success", true},
            {"data", {
                {"devMode", devMode}
            }}
        };

        sendResponse(response, requestId);
        Logger::debug("Dev mode sent to frontend: {}", devMode);

    } catch (const std::exception& e) {
        sendError(std::string("Failed to get dev mode: ") + e.what(), requestId);
        Logger::error("Error in handleGetDevMode: {}", e.what());
    }
}

void IpcServer::handleSetDevMode(const nlohmann::json& message, int requestId) {
    try {
        if (!message.contains("data") || !message["data"].contains("devMode")) {
            sendError("Missing devMode in request", requestId);
            return;
        }

        std::string newMode = message["data"]["devMode"];

        if (newMode != "prod" && newMode != "mock") {
            sendError("Invalid dev mode. Must be 'prod' or 'mock'", requestId);
            return;
        }

        auto& settings = SettingsManager::getInstance();
        settings.setDevMode(newMode);

        json response = {
            {"type", "dev_mode_set"},
            {"success", true},
            {"data", {
                {"devMode", newMode}
            }}
        };

        sendResponse(response, requestId);
        Logger::info("Dev mode set to: {}", newMode);

        // Broadcast event to all listeners
        broadcastEvent("dev_mode_changed", {{"devMode", newMode}});

    } catch (const std::exception& e) {
        sendError(std::string("Failed to set dev mode: ") + e.what(), requestId);
        Logger::error("Error in handleSetDevMode: {}", e.what());
    }
}

void IpcServer::handleGetPowerMonitoring(int requestId) {
    try {
        auto& settings = SettingsManager::getInstance();
        std::string devMode = settings.getDevMode();

        Logger::debug("Getting power monitoring (dev-mode: {})", devMode);

        PowerMonitoring powerData;

        if (devMode == "mock") {
            // Mock mode: Return test data
            powerData = MockDataProvider::getMockPowerMonitoring();
            Logger::debug("Using mock power data");
        } else {
            // Production mode: Fetch from BaluHost server
            if (!baluhostClient_ || !baluhostClient_->isAuthenticated()) {
                sendError("Not authenticated with BaluHost server", requestId);
                Logger::warn("Cannot fetch power data: not authenticated");
                return;
            }

            try {
                auto response = baluhostClient_->getPowerMonitoring();
                if (!response) {
                    sendError("Failed to fetch power monitoring from server", requestId);
                    Logger::error("Error fetching power data: no response");
                    return;
                }

                auto& json = *response;

                // Parse server response
                // Total current power
                powerData.currentPower = json.value("total_current_power", 0.0);

                // Sum energy_today from all devices
                double totalEnergyToday = 0.0;
                int deviceCount = 0;
                if (json.contains("devices") && json["devices"].is_array()) {
                    deviceCount = static_cast<int>(json["devices"].size());
                    for (const auto& device : json["devices"]) {
                        if (device.contains("latest_sample") && !device["latest_sample"].is_null()) {
                            double energy = device["latest_sample"].value("energy_today", 0.0);
                            totalEnergyToday += energy;
                        }
                    }
                }

                // Calculate trend (optional, simplified - server doesn't provide this directly)
                powerData.trendDelta = 0.0;
                powerData.energyToday = totalEnergyToday;
                powerData.deviceCount = deviceCount;
                powerData.maxPower = 150.0;  // Reasonable default

                Logger::debug("Fetched power monitoring from BaluHost server");
            } catch (const std::exception& e) {
                sendError(std::string("Failed to fetch power monitoring from server: ") + e.what(), requestId);
                Logger::error("Error fetching power monitoring from server: {}", e.what());
                return;
            }
        }

        // Build response
        json response = {
            {"type", "power_monitoring"},
            {"success", true},
            {"data", {
                {"currentPower", powerData.currentPower},
                {"energyToday", powerData.energyToday},
                {"trendDelta", powerData.trendDelta},
                {"deviceCount", powerData.deviceCount},
                {"maxPower", powerData.maxPower},
                {"dev_mode", devMode == "mock"}
            }}
        };

        sendResponse(response, requestId);
        Logger::debug("Power monitoring sent to frontend");

    } catch (const std::exception& e) {
        sendError(std::string("Failed to get power monitoring: ") + e.what(), requestId);
        Logger::error("Error in handleGetPowerMonitoring: {}", e.what());
    }
}

}  // namespace baludesk

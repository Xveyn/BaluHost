#include "ipc_server.h"
#include "../sync/sync_engine.h"
#include "../utils/logger.h"
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
            {"folder_id", folderId}
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
            {"folder_id", folderId}
        };
        sendResponse(response, requestId);

    } catch (const std::exception& e) {
        Logger::error("handleResumeSync error: {}", e.what());
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
                {"enabled", folder.enabled}
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

} // namespace baludesk

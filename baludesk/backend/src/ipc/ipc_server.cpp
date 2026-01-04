#include "ipc_server.h"
#include "../sync/sync_engine.h"
#include "../utils/logger.h"
#include "../utils/system_info.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <sstream>
#include <string>

using json = nlohmann::json;

namespace baludesk {

IpcServer::IpcServer(SyncEngine* engine) : engine_(engine) {}

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
            else if (type == "update_sync_folder") {
                handleUpdateSyncFolder(message, requestId);
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
        
        // Note: SyncEngine currently doesn't support serverUrl parameter
        // TODO: Update SyncEngine::login() to accept serverUrl
        bool success = engine_->login(username, password);
        
        if (success) {
            json response = {
                {"success", true},
                {"token", "mock-token-" + username}, // TODO: Get real token from engine
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
    try {
        if (!message.contains("payload")) {
            sendError("Missing payload");
            return;
        }
        
        auto payload = message["payload"];
        std::string localPath = payload.value("local_path", "");
        std::string remotePath = payload.value("remote_path", "");
        
        if (localPath.empty() || remotePath.empty()) {
            sendError("local_path and remote_path required");
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
            sendResponse(response);
        } else {
            sendError("Failed to add sync folder");
        }
        
    } catch (const std::exception& e) {
        Logger::error("handleAddSyncFolder error: {}", e.what());
        sendError(e.what());
    }
}

void IpcServer::handleRemoveSyncFolder(const json& message) {
    try {
        if (!message.contains("payload") || !message["payload"].contains("folder_id")) {
            sendError("Missing folder_id");
            return;
        }
        
        std::string folderId = message["payload"]["folder_id"];
        bool success = engine_->removeSyncFolder(folderId);
        
        json response = {
            {"type", "sync_folder_removed"},
            {"success", success},
            {"folder_id", folderId}
        };
        sendResponse(response);
        
    } catch (const std::exception& e) {
        Logger::error("handleRemoveSyncFolder error: {}", e.what());
        sendError(e.what());
    }
}

void IpcServer::handlePauseSync(const json& message) {
    try {
        if (!message.contains("payload") || !message["payload"].contains("folder_id")) {
            sendError("Missing folder_id");
            return;
        }
        
        std::string folderId = message["payload"]["folder_id"];
        engine_->pauseSync(folderId);
        
        json response = {
            {"type", "sync_paused"},
            {"folder_id", folderId}
        };
        sendResponse(response);
        
    } catch (const std::exception& e) {
        Logger::error("handlePauseSync error: {}", e.what());
        sendError(e.what());
    }
}

void IpcServer::handleResumeSync(const json& message) {
    try {
        if (!message.contains("payload") || !message["payload"].contains("folder_id")) {
            sendError("Missing folder_id");
            return;
        }
        
        std::string folderId = message["payload"]["folder_id"];
        engine_->resumeSync(folderId);
        
        json response = {
            {"type", "sync_resumed"},
            {"folder_id", folderId}
        };
        sendResponse(response);
        
    } catch (const std::exception& e) {
        Logger::error("handleResumeSync error: {}", e.what());
        sendError(e.what());
    }
}

void IpcServer::handleGetSyncState() {
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
        sendResponse(response);
        
    } catch (const std::exception& e) {
        Logger::error("handleGetSyncState error: {}", e.what());
        sendError(e.what());
    }
}

void IpcServer::handleGetFolders() {
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
        sendResponse(response);
        
    } catch (const std::exception& e) {
        Logger::error("handleGetFolders error: {}", e.what());
        sendError(e.what());
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
    sendResponse(event);
}

void IpcServer::handleGetSystemInfo(int requestId) {
    try {
        // Collect system information
        SystemInfo sysInfo = SystemInfoCollector::getSystemInfo();
        
        // Convert to JSON response
        json response = {
            {"type", "system_info"},
            {"success", true},
            {"data", SystemInfoCollector::toJson(sysInfo)}
        };
        
        sendResponse(response, requestId);
        Logger::debug("System info sent to frontend");
        
    } catch (const std::exception& e) {
        sendError(std::string("Failed to get system info: ") + e.what(), requestId);
        Logger::error("Error in handleGetSystemInfo: {}", e.what());
    }
}

} // namespace baludesk

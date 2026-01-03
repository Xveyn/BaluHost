#include "conflict_resolver.h"
#include "../db/database.h"
#include "../api/http_client.h"
#include "../utils/logger.h"
#include <filesystem>
#include <sstream>
#include <chrono>
#include <ctime>

namespace fs = std::filesystem;

namespace baludesk {

ConflictResolver::ConflictResolver(
    Database* db,
    HttpClient* httpClient,
    ResolutionStrategy defaultStrategy
) : db_(db), 
    httpClient_(httpClient), 
    defaultStrategy_(defaultStrategy),
    manualCallback_(nullptr) {
    Logger::info("ConflictResolver initialized with strategy: " + 
                              std::to_string(static_cast<int>(defaultStrategy)));
}

ConflictResolver::~ConflictResolver() {
    Logger::info("ConflictResolver destroyed");
}

// Resolve a single conflict
ResolutionResult ConflictResolver::resolve(
    const std::string& localPath,
    const std::string& remotePath,
    const std::chrono::system_clock::time_point& localTimestamp,
    const std::chrono::system_clock::time_point& remoteTimestamp,
    ResolutionStrategy strategy
) {
    Logger::info("Resolving conflict for: " + localPath + 
                              " with strategy " + std::to_string(static_cast<int>(strategy)));
    
    ResolutionResult result;
    result.success = false;
    
    try {
        switch (strategy) {
            case ResolutionStrategy::LAST_WRITE_WINS:
                result = resolveLastWriteWins(localPath, remotePath, 
                                             localTimestamp, remoteTimestamp);
                break;
                
            case ResolutionStrategy::KEEP_BOTH:
                result = resolveKeepBoth(localPath, remotePath);
                break;
                
            case ResolutionStrategy::MANUAL:
                result = resolveManual(localPath, remotePath);
                break;
                
            case ResolutionStrategy::LOCAL_WINS:
                // Always upload local version
                if (httpClient_->uploadFile(localPath, remotePath)) {
                    result.success = true;
                    result.action = "uploaded";
                    result.finalPath = remotePath;
                    Logger::info("LOCAL_WINS: Uploaded " + localPath);
                } else {
                    result.errorMessage = "Upload failed";
                }
                break;
                
            case ResolutionStrategy::REMOTE_WINS:
                // Always download remote version
                if (httpClient_->downloadFile(remotePath, localPath)) {
                    result.success = true;
                    result.action = "downloaded";
                    result.finalPath = localPath;
                    Logger::info("REMOTE_WINS: Downloaded " + remotePath);
                } else {
                    result.errorMessage = "Download failed";
                }
                break;
                
            default:
                result.errorMessage = "Unknown resolution strategy";
                Logger::error("Unknown strategy: " + 
                                          std::to_string(static_cast<int>(strategy)));
                break;
        }
        
        // Log conflict resolution to database
        if (result.success) {
            Conflict conflict;
            conflict.id = db_->generateId();
            conflict.path = localPath;
            conflict.folderId = ""; // TODO: Get from context
            conflict.localModified = "";  // TODO: Add timestamp
            conflict.remoteModified = ""; // TODO: Add timestamp
            conflict.resolution = result.action;
            db_->logConflict(conflict);
        }
        
    } catch (const std::exception& e) {
        result.success = false;
        result.errorMessage = "Exception: " + std::string(e.what());
        Logger::error("Conflict resolution failed: " + result.errorMessage);
    }
    
    return result;
}

// Resolve using default strategy
ResolutionResult ConflictResolver::resolveAuto(
    const std::string& localPath,
    const std::string& remotePath,
    const std::chrono::system_clock::time_point& localTimestamp,
    const std::chrono::system_clock::time_point& remoteTimestamp
) {
    return resolve(localPath, remotePath, localTimestamp, remoteTimestamp, 
                  defaultStrategy_);
}

// Set manual resolution callback
void ConflictResolver::setManualCallback(ManualResolutionCallback callback) {
    manualCallback_ = callback;
    Logger::info("Manual resolution callback set");
}

// Change default strategy
void ConflictResolver::setDefaultStrategy(ResolutionStrategy strategy) {
    defaultStrategy_ = strategy;
    Logger::info("Default strategy changed to: " + 
                              std::to_string(static_cast<int>(strategy)));
}

// Strategy: Last-Write-Wins
ResolutionResult ConflictResolver::resolveLastWriteWins(
    const std::string& localPath,
    const std::string& remotePath,
    const std::chrono::system_clock::time_point& localTimestamp,
    const std::chrono::system_clock::time_point& remoteTimestamp
) {
    ResolutionResult result;
    
    if (localTimestamp > remoteTimestamp) {
        // Local is newer -> upload
        Logger::info("LAST_WRITE_WINS: Local is newer, uploading");
        
        if (httpClient_->uploadFile(localPath, remotePath)) {
            result.success = true;
            result.action = "uploaded";
            result.finalPath = remotePath;
        } else {
            result.errorMessage = "Upload failed";
        }
        
    } else {
        // Remote is newer (or equal) -> download
        Logger::info("LAST_WRITE_WINS: Remote is newer, downloading");
        
        if (httpClient_->downloadFile(remotePath, localPath)) {
            result.success = true;
            result.action = "downloaded";
            result.finalPath = localPath;
        } else {
            result.errorMessage = "Download failed";
        }
    }
    
    return result;
}

// Strategy: Keep Both
ResolutionResult ConflictResolver::resolveKeepBoth(
    const std::string& localPath,
    const std::string& remotePath
) {
    ResolutionResult result;
    
    Logger::info("KEEP_BOTH: Keeping both versions");
    
    try {
        // Parse file extension
        fs::path path(localPath);
        std::string stem = path.stem().string();
        std::string extension = path.extension().string();
        std::string parentPath = path.parent_path().string();
        
        // Generate conflict filename
        auto now = std::chrono::system_clock::now();
        auto timestamp = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << stem << "_conflict_" << timestamp << extension;
        std::string conflictName = ss.str();
        
        std::string conflictLocalPath = parentPath + "/" + conflictName;
        std::string conflictRemotePath = remotePath + "_conflict_" + 
                                        std::to_string(timestamp);
        
        // Download remote to conflict file
        if (!httpClient_->downloadFile(remotePath, conflictLocalPath)) {
            result.errorMessage = "Failed to download remote version";
            return result;
        }
        
        // Upload original local to remote
        if (!httpClient_->uploadFile(localPath, remotePath)) {
            result.errorMessage = "Failed to upload local version";
            return result;
        }
        
        // Upload conflict file to remote as well
        if (!httpClient_->uploadFile(conflictLocalPath, conflictRemotePath)) {
            result.errorMessage = "Failed to upload conflict version";
            return result;
        }
        
        result.success = true;
        result.action = "renamed";
        result.finalPath = conflictLocalPath;
        
        Logger::info("KEEP_BOTH: Created conflict file: " + conflictName);
        
    } catch (const std::exception& e) {
        result.errorMessage = "Exception: " + std::string(e.what());
        Logger::error("KEEP_BOTH failed: " + result.errorMessage);
    }
    
    return result;
}

// Strategy: Manual
ResolutionResult ConflictResolver::resolveManual(
    const std::string& localPath,
    const std::string& remotePath
) {
    ResolutionResult result;
    
    if (!manualCallback_) {
        result.errorMessage = "No manual callback set";
        Logger::error("MANUAL strategy requires callback");
        return result;
    }
    
    Logger::info("MANUAL: Calling user callback");
    
    try {
        // Call user callback to decide
        ResolutionStrategy userChoice = manualCallback_(localPath, remotePath);
        
        // Resolve with user's choice (but not MANUAL again to avoid infinite loop)
        if (userChoice == ResolutionStrategy::MANUAL) {
            result.errorMessage = "User callback returned MANUAL again";
            Logger::error("Invalid callback result");
            return result;
        }
        
        // Recursive call with user's choice
        result = resolve(localPath, remotePath, 
                        std::chrono::system_clock::now(),
                        std::chrono::system_clock::now(),
                        userChoice);
        result.action = "manual";
        
    } catch (const std::exception& e) {
        result.errorMessage = "Callback exception: " + std::string(e.what());
        Logger::error("Manual callback failed: " + result.errorMessage);
    }
    
    return result;
}

} // namespace baludesk

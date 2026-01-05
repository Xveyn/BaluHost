#include "sync/sync_engine.h"
#include "sync/file_watcher_v2.h"
#include "api/http_client.h"
#include "db/database.h"
#include "sync/conflict_resolver.h"
#include "sync/change_detector.h"
#include "utils/logger.h"
#include <chrono>
#include <thread>
#include <filesystem>
#include <ctime>
#include <cmath>
#include <sstream>
#include <iomanip>

namespace baludesk {

SyncEngine::SyncEngine() {
    stats_.status = SyncStatus::IDLE;
    stats_.uploadSpeed = 0;
    stats_.downloadSpeed = 0;
    stats_.pendingUploads = 0;
    stats_.pendingDownloads = 0;
}

SyncEngine::~SyncEngine() {
    stop();
}

bool SyncEngine::initialize(const std::string& dbPath, const std::string& serverUrl) {
    try {
        Logger::info("Initializing SyncEngine...");
        
        // Initialize database
        database_ = std::make_unique<Database>(dbPath);
        if (!database_->initialize()) {
            Logger::error("Failed to initialize database");
            return false;
        }

        // Initialize HTTP client
        httpClient_ = std::make_unique<HttpClient>(serverUrl);

        // Initialize other components
        fileWatcher_ = std::make_unique<FileWatcher>();
        conflictResolver_ = std::make_unique<ConflictResolver>(
            database_.get(), 
            httpClient_.get()
        );
        changeDetector_ = std::make_unique<ChangeDetector>(
            database_.get(),
            httpClient_.get()
        );

        // Set file watcher callback
        fileWatcher_->setCallback([this](const FileEvent& event) {
            std::lock_guard<std::mutex> lock(queueMutex_);
            eventQueue_.push(event);
        });

        Logger::info("SyncEngine initialized successfully");
        return true;
    } catch (const std::exception& e) {
        Logger::error("Failed to initialize SyncEngine: " + std::string(e.what()));
        return false;
    }
}

void SyncEngine::start() {
    if (running_) {
        Logger::warn("SyncEngine already running");
        return;
    }

    Logger::info("Starting SyncEngine...");
    running_ = true;
    stats_.status = SyncStatus::IDLE;

    // Start sync loop in separate thread
    syncThread_ = std::thread([this]() {
        syncLoop();
    });

    // Start file watchers for all enabled folders
    auto folders = getSyncFolders();
    for (const auto& folder : folders) {
        if (folder.enabled && folder.status != SyncStatus::PAUSED) {
            fileWatcher_->watch(folder.localPath);
        }
    }

    notifyStatusChange();
}

void SyncEngine::stop() {
    if (!running_) {
        return;
    }

    Logger::info("Stopping SyncEngine...");
    running_ = false;

    // Stop file watcher
    if (fileWatcher_) {
        fileWatcher_->stop();
    }

    // Wait for sync thread
    if (syncThread_.joinable()) {
        syncThread_.join();
    }

    stats_.status = SyncStatus::IDLE;
    notifyStatusChange();
}

bool SyncEngine::isRunning() const {
    return running_;
}

bool SyncEngine::login(const std::string& username, const std::string& password) {
    Logger::info("Attempting login for user: " + username);
    
    if (!httpClient_) {
        Logger::error("HTTP client not initialized");
        return false;
    }

    if (httpClient_->login(username, password)) {
        authenticated_ = true;
        Logger::info("Login successful");
        return true;
    }

    authenticated_ = false;
    Logger::error("Login failed");
    return false;
}

void SyncEngine::logout() {
    authenticated_ = false;
    if (httpClient_) {
        httpClient_->clearAuthToken();
    }
    Logger::info("Logged out");
}

bool SyncEngine::isAuthenticated() const {
    return authenticated_;
}

bool SyncEngine::addSyncFolder(SyncFolder& folder) {
    Logger::info("Adding sync folder: " + folder.localPath + " -> " + folder.remotePath);
    
    // Generate ID if not set
    if (folder.id.empty()) {
        folder.id = database_->generateId();
    }
    
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    folder.createdAt = std::to_string(std::time(nullptr));

    if (database_->addSyncFolder(folder)) {
        // Start watching this folder
        if (running_) {
            fileWatcher_->watch(folder.localPath);
        }
        
        // Trigger initial sync
        triggerSync(folder.id);
        
        return true;
    }

    return false;
}

bool SyncEngine::removeSyncFolder(const std::string& folderId) {
    Logger::info("Removing sync folder: " + folderId);
    
    auto folder = database_->getSyncFolder(folderId);
    if (!folder.id.empty()) {
        fileWatcher_->unwatch(folder.localPath);
        return database_->removeSyncFolder(folderId);
    }
    
    return false;
}

bool SyncEngine::pauseSync(const std::string& folderId) {
    auto folder = database_->getSyncFolder(folderId);
    if (!folder.id.empty()) {
        folder.status = SyncStatus::PAUSED;
        fileWatcher_->unwatch(folder.localPath);
        return database_->updateSyncFolder(folder);
    }
    return false;
}

bool SyncEngine::resumeSync(const std::string& folderId) {
    auto folder = database_->getSyncFolder(folderId);
    if (!folder.id.empty()) {
        folder.status = SyncStatus::IDLE;
        fileWatcher_->watch(folder.localPath);
        triggerSync(folderId);
        return database_->updateSyncFolder(folder);
    }
    return false;
}

bool SyncEngine::updateSyncFolderSettings(const std::string& folderId, const std::string& conflictResolution) {
    auto folder = database_->getSyncFolder(folderId);
    if (!folder.id.empty()) {
        // Update the conflict resolution setting for the folder
        // Store in the folder's settings - this may require extending SyncFolder struct
        // For now, we'll just log the update
        Logger::info("Updated conflict resolution for folder {} to: {}", folderId, conflictResolution);
        
        // TODO: Persist the conflict resolution setting to the database
        // This might require adding a conflict_resolution field to the sync_folders table
        
        return true;
    }
    return false;
}

// Helper function to calculate folder size recursively
uint64_t calculateFolderSize(const std::string& path) {
    uint64_t totalSize = 0;
    try {
        namespace fs = std::filesystem;
        for (const auto& entry : fs::recursive_directory_iterator(path)) {
            if (fs::is_regular_file(entry)) {
                totalSize += fs::file_size(entry);
            }
        }
    } catch (const std::exception& e) {
        Logger::warn("Error calculating folder size for {}: {}", path, e.what());
    }
    return totalSize;
}

std::vector<SyncFolder> SyncEngine::getSyncFolders() const {
    auto folders = database_->getSyncFolders();
    
    // Calculate size for each folder
    for (auto& folder : folders) {
        folder.size = calculateFolderSize(folder.localPath);
    }
    
    return folders;
}

void SyncEngine::triggerSync(const std::string& folderId) {
    Logger::info("Triggering sync" + (folderId.empty() ? "" : " for folder: " + folderId));
    
    // Implementation will scan for changes and sync
    // This is a simplified version - full implementation in next iteration
}

SyncStats SyncEngine::getSyncState() const {
    std::lock_guard<std::mutex> lock(const_cast<std::mutex&>(statsMutex_));
    return stats_;
}

void SyncEngine::setStatusCallback(StatusCallback callback) {
    statusCallback_ = callback;
}

void SyncEngine::setFileChangeCallback(FileChangeCallback callback) {
    fileChangeCallback_ = callback;
}

void SyncEngine::setErrorCallback(ErrorCallback callback) {
    errorCallback_ = callback;
}

void SyncEngine::syncLoop() {
    Logger::info("Sync loop started");
    
    while (running_) {
        try {
            // Process file events from queue
            {
                std::lock_guard<std::mutex> lock(queueMutex_);
                while (!eventQueue_.empty()) {
                    auto event = eventQueue_.front();
                    eventQueue_.pop();
                    processFileEvent(event);
                }
            }

            // Periodic sync check (every 30 seconds)
            auto folders = getSyncFolders();
            for (const auto& folder : folders) {
                if (folder.enabled && folder.status != SyncStatus::PAUSED) {
                    fetchRemoteChanges(folder);
                }
            }

            updateStats();
            
        } catch (const std::exception& e) {
            Logger::error("Error in sync loop: " + std::string(e.what()));
            if (errorCallback_) {
                errorCallback_(e.what());
            }
        }

        // Sleep for a bit
        std::this_thread::sleep_for(std::chrono::seconds(30));
    }
    
    Logger::info("Sync loop stopped");
}

void SyncEngine::processFileEvent(const FileEvent& event) {
    Logger::debug("Processing file event: " + event.path);
    
    // Find which folder this belongs to
    auto folders = getSyncFolders();
    for (const auto& folder : folders) {
        if (event.path.find(folder.localPath) == 0) {
            // File belongs to this sync folder
            std::string relativePath = event.path.substr(folder.localPath.length());
            std::string remotePath = folder.remotePath + relativePath;
            
            switch (event.action) {
                case FileAction::CREATED:
                case FileAction::MODIFIED:
                    uploadFile(event.path, remotePath);
                    break;
                case FileAction::DELETED:
                    // Handle deletion
                    break;
            }
            
            if (fileChangeCallback_) {
                fileChangeCallback_(event);
            }
            break;
        }
    }
}

void SyncEngine::scanLocalChanges(const SyncFolder& folder) {
    Logger::info("Scanning local changes for: " + folder.localPath);
    
    if (!changeDetector_) {
        Logger::error("ChangeDetector not initialized");
        return;
    }
    
    try {
        // Get current timestamp
        auto now = std::chrono::system_clock::now();
        auto now_time_t = std::chrono::system_clock::to_time_t(now);
        std::tm tm;
        localtime_s(&tm, &now_time_t);
        char buffer[32];
        std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S", &tm);
        std::string currentTimestamp(buffer);
        
        // Detect local changes
        auto localChanges = changeDetector_->detectLocalChanges(folder.id, folder.localPath);
        Logger::debug("Found {} local changes", localChanges.size());
        
        // Update metadata and queue uploads
        for (const auto& change : localChanges) {
            std::string fullPath = folder.localPath + "/" + change.path;
            FileMetadata metadata;
            metadata.path = fullPath;
            metadata.folderId = folder.id;
            metadata.size = change.size;
            metadata.isDirectory = false;
            metadata.modifiedAt = std::to_string(std::chrono::system_clock::to_time_t(change.timestamp));
            metadata.syncStatus = "pending_upload";
            if (change.hash.has_value()) metadata.checksum = change.hash.value();
            database_->upsertFileMetadata(metadata);
            
            if (change.type != ChangeType::DELETED) {
                std::lock_guard<std::mutex> lock(queueMutex_);
                FileEvent event;
                event.path = fullPath;
                event.action = (change.type == ChangeType::CREATED) ? FileAction::CREATED : FileAction::MODIFIED;
                event.size = change.size;
                event.timestamp = currentTimestamp;
                eventQueue_.push(event);
            }
        }
    } catch (const std::exception& e) {
        Logger::error("Error scanning local changes: {}", e.what());
    }
}

void SyncEngine::fetchRemoteChanges(const SyncFolder& folder) {
    Logger::info("Fetching remote changes for: " + folder.remotePath);
    
    if (!authenticated_) {
        Logger::warn("Cannot fetch remote changes: not authenticated");
        return;
    }
    if (!httpClient_) {
        Logger::error("HTTP client not initialized");
        return;
    }
    
    try {
        auto lastSyncFolder = database_->getSyncFolder(folder.id);
        std::string lastSyncTimestamp = lastSyncFolder.lastSync.empty() ? "1970-01-01T00:00:00" : lastSyncFolder.lastSync;
        auto remoteChanges = httpClient_->getChangesSince(lastSyncTimestamp);
        Logger::debug("Found {} remote changes", remoteChanges.size());
        
        for (const auto& remoteChange : remoteChanges) {
            if (remoteChange.path.find(folder.remotePath) != 0) continue;
            std::string relativePath = remoteChange.path.substr(folder.remotePath.length());
            std::string localPath = folder.localPath + relativePath;
            Logger::debug("Remote change detected: {} ({})", localPath, remoteChange.action);
            
            if (remoteChange.action == "deleted") {
                database_->deleteFileMetadata(localPath);
            } else if (remoteChange.action == "created" || remoteChange.action == "modified") {
                FileMetadata metadata;
                metadata.path = localPath;
                metadata.folderId = folder.id;
                metadata.syncStatus = "pending_download";
                database_->upsertFileMetadata(metadata);
                
                std::lock_guard<std::mutex> lock(queueMutex_);
                FileEvent event;
                event.path = localPath;
                event.action = (remoteChange.action == "created") ? FileAction::CREATED : FileAction::MODIFIED;
                event.timestamp = remoteChange.timestamp;
                eventQueue_.push(event);
            }
        }
        database_->updateSyncFolderTimestamp(folder.id);
    } catch (const std::exception& e) {
        Logger::error("Error fetching remote changes: {}", e.what());
    }
}

void SyncEngine::uploadFile(const std::string& localPath, const std::string& remotePath) {
    Logger::info("Uploading: " + localPath + " -> " + remotePath);
    
    if (!authenticated_) {
        Logger::error("Not authenticated");
        return;
    }

    try {
        stats_.status = SyncStatus::SYNCING;
        notifyStatusChange();
        
        if (httpClient_->uploadFile(localPath, remotePath)) {
            Logger::info("Upload successful: " + localPath);
        } else {
            Logger::error("Upload failed: " + localPath);
        }
        
        stats_.status = SyncStatus::IDLE;
        notifyStatusChange();
    } catch (const std::exception& e) {
        std::string errorMsg = "Upload error: ";
        errorMsg += e.what();
        Logger::error(errorMsg);
        stats_.status = SyncStatus::SYNC_ERROR;
        notifyStatusChange();
    }
}

void SyncEngine::downloadFile(const std::string& remotePath, const std::string& localPath) {
    Logger::info("Downloading: {} -> {}", remotePath, localPath);
    
    if (!authenticated_) {
        Logger::error("Cannot download: not authenticated");
        return;
    }
    if (!httpClient_) {
        Logger::error("HTTP client not initialized");
        return;
    }
    
    try {
        std::filesystem::path localPathObj(localPath);
        std::filesystem::create_directories(localPathObj.parent_path());
        
        stats_.status = SyncStatus::SYNCING;
        notifyStatusChange();
        
        // Use retry logic for download with exponential backoff
        bool success = retryWithBackoff([this, &remotePath, &localPath]() {
            return httpClient_->downloadFileWithProgress(
                remotePath, localPath,
                [this](const DownloadProgress& progress) {
                    std::lock_guard<std::mutex> lock(statsMutex_);
                    stats_.downloadSpeed = static_cast<uint64_t>(progress.bytesDownloaded);
                }
            );
        }, 3, 1000);  // 3 retries, starting at 1000ms
        
        if (success) {
            Logger::info("Download successful: {}", localPath);
            if (auto metadata = database_->getFileMetadata(localPath)) {
                FileMetadata updated = metadata.value();
                updated.syncStatus = "synced";
                database_->upsertFileMetadata(updated);
            }
            if (stats_.pendingDownloads > 0) {
                stats_.pendingDownloads--;
            }
        } else {
            Logger::error("Download failed after retries: {}", remotePath);
            stats_.status = SyncStatus::SYNC_ERROR;
        }
        stats_.status = SyncStatus::IDLE;
        notifyStatusChange();
    } catch (const std::exception& e) {
        Logger::error("Download error: {}", e.what());
        stats_.status = SyncStatus::SYNC_ERROR;
        notifyStatusChange();
    }
}

void SyncEngine::handleConflict(const std::string& path) {
    Logger::warn("Conflict detected: {}", path);
    
    if (!database_) {
        Logger::error("Database not initialized");
        return;
    }
    if (!conflictResolver_) {
        Logger::error("ConflictResolver not initialized");
        return;
    }
    
    try {
        auto localMetadata = database_->getFileMetadata(path);
        if (!localMetadata) {
            Logger::warn("File metadata not found for conflict: {}", path);
            return;
        }
        
        auto localTime = std::chrono::system_clock::from_time_t(std::stoll(localMetadata->modifiedAt));
        Conflict conflict;
        conflict.id = database_->generateId();
        conflict.path = path;
        conflict.folderId = localMetadata->folderId;
        conflict.localModified = localMetadata->modifiedAt;
        conflict.remoteModified = std::to_string(std::chrono::system_clock::to_time_t(std::chrono::system_clock::now()));
        conflict.resolution = "pending";
        database_->logConflict(conflict);
        
        auto resolution = conflictResolver_->resolveAuto(path, path, localTime, std::chrono::system_clock::now());
        if (resolution.success) {
            Logger::info("Conflict resolved automatically: {} ({})", path, resolution.action);
            database_->resolveConflict(conflict.id, resolution.action);
            if (resolution.finalPath != path) {
                if (auto metadata = database_->getFileMetadata(path)) {
                    FileMetadata updated = metadata.value();
                    updated.path = resolution.finalPath;
                    database_->upsertFileMetadata(updated);
                    database_->deleteFileMetadata(path);
                }
            }
        } else {
            Logger::warn("Could not resolve conflict automatically: {}", path);
            if (errorCallback_) errorCallback_("Conflict at: " + path + " - Manual resolution needed");
        }
    } catch (const std::exception& e) {
        Logger::error("Error handling conflict: {}", e.what());
    }
}

// Sprint 3 methods - now active
void SyncEngine::triggerBidirectionalSync(const std::string& folderId) {
    Logger::info("Triggering bidirectional sync for folder: " + 
                (folderId.empty() ? "all" : folderId));
    
    auto folders = getSyncFolders();
    
    for (const auto& folder : folders) {
        if (folder.enabled && folder.status != SyncStatus::PAUSED) {
            if (folderId.empty() || folder.id == folderId) {
                syncBidirectional(folder);
            }
        }
    }
}

void SyncEngine::syncBidirectional(const SyncFolder& folder) {
    Logger::info("Starting bidirectional sync for: " + folder.localPath);
    
    try {
        stats_.status = SyncStatus::SYNCING;
        notifyStatusChange();
        
        // 1. Detect local changes
        auto localChanges = changeDetector_->detectLocalChanges(
            folder.id,
            folder.localPath
        );
        Logger::info("Detected " + std::to_string(localChanges.size()) + " local changes");
        
        // 2. Detect remote changes
        auto lastSync = std::chrono::system_clock::now() - std::chrono::hours(24); // Last 24h
        auto remoteChanges = changeDetector_->detectRemoteChanges(
            folder.id,
            lastSync
        );
        Logger::info("Detected " + std::to_string(remoteChanges.size()) + " remote changes");
        
        // 3. Detect conflicts
        auto conflicts = changeDetector_->detectConflicts(localChanges, remoteChanges);
        Logger::info("Detected " + std::to_string(conflicts.size()) + " conflicts");
        
        // 4. Handle conflicts first
        for (const auto& conflict : conflicts) {
            resolveConflict(conflict, folder);
        }
        
        // 5. Process non-conflicting remote changes (downloads)
        for (const auto& change : remoteChanges) {
            // Skip if in conflict list
            bool isConflict = false;
            for (const auto& conflict : conflicts) {
                if (conflict.path == change.path) {
                    isConflict = true;
                    break;
                }
            }
            
            if (!isConflict) {
                handleRemoteChange(change, folder);
            }
        }
        
        // 6. Process non-conflicting local changes (uploads)
        for (const auto& change : localChanges) {
            // Skip if in conflict list
            bool isConflict = false;
            for (const auto& conflict : conflicts) {
                if (conflict.path == change.path) {
                    isConflict = true;
                    break;
                }
            }
            
            if (!isConflict) {
                handleLocalChange(change, folder);
            }
        }
        
        // 7. Update last sync timestamp
        database_->updateSyncFolderTimestamp(folder.id);
        
        stats_.status = SyncStatus::IDLE;
        notifyStatusChange();
        
        Logger::info("Bidirectional sync completed for: " + folder.localPath);
        
    } catch (const std::exception& e) {
        Logger::error("Bidirectional sync failed: " + std::string(e.what()));
        stats_.status = SyncStatus::SYNC_ERROR;
        notifyStatusChange();
    }
}

void SyncEngine::handleRemoteChange(const DetectedChange& change, const SyncFolder& folder) {
    std::string localPath = folder.localPath + "/" + change.path;
    std::string remotePath = folder.remotePath + "/" + change.path;
    
    switch (change.type) {
        case ChangeType::CREATED:
        case ChangeType::MODIFIED:
            Logger::info("Downloading remote change: " + change.path);
            if (httpClient_->downloadFile(remotePath, localPath)) {
                // Convert timestamp to ISO8601 string
                auto time = std::chrono::system_clock::to_time_t(change.timestamp);
                std::tm timeInfo;
                gmtime_s(&timeInfo, &time);
                std::stringstream ss;
                ss << std::put_time(&timeInfo, "%Y-%m-%dT%H:%M:%SZ");
                
                database_->upsertFileMetadata(
                    change.path,
                    folder.id,
                    change.size,
                    change.hash.value_or(""),
                    ss.str()
                );
                stats_.pendingDownloads++;
                notifyStatusChange();
            }
            break;
            
        case ChangeType::DELETED:
            Logger::info("Deleting local file (remote deleted): " + change.path);
            std::filesystem::remove(localPath);
            database_->deleteFileMetadata(change.path);
            break;
    }
}

void SyncEngine::handleLocalChange(const DetectedChange& change, const SyncFolder& folder) {
    std::string localPath = folder.localPath + "/" + change.path;
    std::string remotePath = folder.remotePath + "/" + change.path;
    
    switch (change.type) {
        case ChangeType::CREATED:
        case ChangeType::MODIFIED:
            Logger::info("Uploading local change: " + change.path);
            // Use retry logic for upload with exponential backoff
            if (retryWithBackoff([this, &localPath, &remotePath]() {
                return httpClient_->uploadFile(localPath, remotePath);
            }, 3, 1000)) {  // 3 retries, starting at 1000ms
                // Convert timestamp to ISO8601 string
                auto time = std::chrono::system_clock::to_time_t(change.timestamp);
                std::tm timeInfo;
                gmtime_s(&timeInfo, &time);
                std::stringstream ss;
                ss << std::put_time(&timeInfo, "%Y-%m-%dT%H:%M:%SZ");
                
                database_->upsertFileMetadata(
                    change.path,
                    folder.id,
                    change.size,
                    change.hash.value_or(""),
                    ss.str()
                );
                stats_.pendingUploads++;
                notifyStatusChange();
            } else {
                Logger::error("Upload failed after retries: {}", change.path);
            }
            break;
            
        case ChangeType::DELETED:
            Logger::info("Deleting remote file (local deleted): " + change.path);
            // Use retry logic for delete with exponential backoff
            if (retryWithBackoff([this, &remotePath]() {
                return httpClient_->deleteFile(remotePath);
            }, 3, 1000)) {  // 3 retries, starting at 1000ms
                database_->deleteFileMetadata(change.path);
            } else {
                Logger::error("Delete failed after retries: {}", change.path);
            }
            break;
    }
}

void SyncEngine::resolveConflict(const ConflictInfo& conflict, const SyncFolder& folder) {
    Logger::warn("Resolving conflict for: " + conflict.path);
    
    std::string localPath = folder.localPath + "/" + conflict.path;
    std::string remotePath = folder.remotePath + "/" + conflict.path;
    
    // Use ConflictResolver with default strategy (Last-Write-Wins)
    auto result = conflictResolver_->resolveAuto(
        localPath,
        remotePath,
        conflict.localTimestamp,
        conflict.remoteTimestamp
    );
    
    if (result.success) {
        Logger::info("Conflict resolved: " + conflict.path + " -> " + result.action);
    } else {
        Logger::error("Conflict resolution failed: " + result.errorMessage);
    }
}

void SyncEngine::updateStats() {
    std::lock_guard<std::mutex> lock(statsMutex_);
    
    // Update statistics
    // TODO: Calculate real values
    stats_.lastSync = std::to_string(std::time(nullptr));
}

void SyncEngine::notifyStatusChange() {
    if (statusCallback_) {
        statusCallback_(getSyncState());
    }
}

} // namespace baludesk

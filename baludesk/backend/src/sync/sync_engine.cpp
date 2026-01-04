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

std::vector<SyncFolder> SyncEngine::getSyncFolders() const {
    return database_->getSyncFolders();
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
    // TODO: Implement local change scanning
    Logger::debug("Scanning local changes for: " + folder.localPath);
}

void SyncEngine::fetchRemoteChanges(const SyncFolder& folder) {
    // TODO: Implement remote change fetching
    Logger::debug("Fetching remote changes for: " + folder.remotePath);
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
    Logger::info("Downloading: " + remotePath + " -> " + localPath);
    
    // TODO: Implement download
}

void SyncEngine::handleConflict(const std::string& path) {
    Logger::warn("Conflict detected: " + path);
    
    // TODO: Implement conflict handling
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
            if (httpClient_->uploadFile(localPath, remotePath)) {
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
            }
            break;
            
        case ChangeType::DELETED:
            Logger::info("Deleting remote file (local deleted): " + change.path);
            httpClient_->deleteFile(remotePath);
            database_->deleteFileMetadata(change.path);
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

#include "change_detector.h"
#include "../db/database.h"
#include "../api/http_client.h"
#include "../utils/logger.h"
#include <filesystem>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <chrono>
#include <algorithm>

namespace fs = std::filesystem;

namespace baludesk {

ChangeDetector::ChangeDetector(Database* db, HttpClient* httpClient)
    : db_(db), httpClient_(httpClient) {
    Logger::info("ChangeDetector initialized");
}

ChangeDetector::~ChangeDetector() {
    Logger::info("ChangeDetector destroyed");
}

// Remote change detection
std::vector<DetectedChange> ChangeDetector::detectRemoteChanges(
    const std::string& syncFolderId,
    const std::chrono::system_clock::time_point& since
) {
    Logger::info("Detecting remote changes for folder: " + syncFolderId);
    
    std::vector<DetectedChange> changes;
    
    try {
        // Convert timestamp to ISO8601 string
        auto sinceTime = std::chrono::system_clock::to_time_t(since);
        std::tm timeInfo;
        gmtime_s(&timeInfo, &sinceTime);
        std::stringstream ss;
        ss << std::put_time(&timeInfo, "%Y-%m-%dT%H:%M:%SZ");
        std::string sinceStr = ss.str();
        
        // Call remote API: GET /api/sync/changes?folderId=X&since=Y
        std::string endpoint = "/api/sync/changes?folderId=" + syncFolderId + 
                              "&since=" + sinceStr;
        
        // TODO: httpClient_->get() needs to be implemented
        // For now, simulate with listFiles()
        auto remoteFiles = httpClient_->listFiles("/" + syncFolderId);
        
        // Compare with local metadata
        for (const auto& remoteFile : remoteFiles) {
            auto localMeta = db_->getFileMetadata(remoteFile.path);
            
            if (!localMeta) {
                // New file on remote
                DetectedChange change;
                change.path = remoteFile.path;
                change.type = ChangeType::CREATED;
                change.timestamp = std::chrono::system_clock::now(); // TODO: parse from API
                change.size = remoteFile.size;
                change.isRemote = true;
                changes.push_back(change);
                
                Logger::debug("Remote CREATED: " + remoteFile.path);
            } else {
                // Check if modified
                if (localMeta->size != remoteFile.size || 
                    localMeta->checksum != remoteFile.hash) {
                    DetectedChange change;
                    change.path = remoteFile.path;
                    change.type = ChangeType::MODIFIED;
                    change.timestamp = std::chrono::system_clock::now();
                    change.hash = remoteFile.hash;
                    change.size = remoteFile.size;
                    change.isRemote = true;
                    changes.push_back(change);
                    
                    Logger::debug("Remote MODIFIED: " + remoteFile.path);
                }
            }
        }
        
        // Detect remote deletions
        // Get all local files for this folder
        auto localFiles = db_->getFilesInFolder(syncFolderId);
        for (const auto& localFile : localFiles) {
            bool foundRemote = false;
            for (const auto& remoteFile : remoteFiles) {
                if (remoteFile.path == localFile.path) {
                    foundRemote = true;
                    break;
                }
            }
            
            if (!foundRemote) {
                DetectedChange change;
                change.path = localFile.path;
                change.type = ChangeType::DELETED;
                change.timestamp = std::chrono::system_clock::now();
                change.isRemote = true;
                changes.push_back(change);
                
                Logger::debug("Remote DELETED: " + localFile.path);
            }
        }
        
        Logger::info("Detected " + std::to_string(changes.size()) + 
                                  " remote changes");
        
    } catch (const std::exception& e) {
        Logger::error("Failed to detect remote changes: " + 
                                   std::string(e.what()));
    }
    
    return changes;
}

// Local change detection
std::vector<DetectedChange> ChangeDetector::detectLocalChanges(
    const std::string& syncFolderId,
    const std::string& localPath
) {
    Logger::info("Detecting local changes in: " + localPath);
    
    std::vector<DetectedChange> changes;
    
    try {
        // Scan local directory
        if (!fs::exists(localPath)) {
            Logger::warn("Local path does not exist: " + localPath);
            return changes;
        }
        
        // Recursive directory scan
        scanDirectory(localPath, localPath, changes);
        
        // Detect local deletions (in DB but not on filesystem)
        auto dbFiles = db_->getFilesInFolder(syncFolderId);
        for (const auto& dbFile : dbFiles) {
            std::string fullPath = localPath + "/" + dbFile.path;
            if (!fs::exists(fullPath)) {
                DetectedChange change;
                change.path = dbFile.path;
                change.type = ChangeType::DELETED;
                change.timestamp = std::chrono::system_clock::now();
                change.isRemote = false;
                changes.push_back(change);
                
                Logger::debug("Local DELETED: " + dbFile.path);
            }
        }
        
        Logger::info("Detected " + std::to_string(changes.size()) + 
                                  " local changes");
        
    } catch (const std::exception& e) {
        Logger::error("Failed to detect local changes: " + 
                                   std::string(e.what()));
    }
    
    return changes;
}

// Conflict detection
std::vector<ConflictInfo> ChangeDetector::detectConflicts(
    const std::vector<DetectedChange>& localChanges,
    const std::vector<DetectedChange>& remoteChanges
) {
    Logger::info("Detecting conflicts...");
    
    std::vector<ConflictInfo> conflicts;
    
    // Find files that were modified on both sides
    for (const auto& localChange : localChanges) {
        if (localChange.type != ChangeType::MODIFIED) continue;
        
        for (const auto& remoteChange : remoteChanges) {
            if (remoteChange.type != ChangeType::MODIFIED) continue;
            
            if (localChange.path == remoteChange.path) {
                // Both sides modified the same file!
                // Check if hashes are different
                if (localChange.hash && remoteChange.hash && 
                    localChange.hash != remoteChange.hash) {
                    
                    ConflictInfo conflict;
                    conflict.path = localChange.path;
                    conflict.localTimestamp = localChange.timestamp;
                    conflict.remoteTimestamp = remoteChange.timestamp;
                    conflict.localHash = localChange.hash.value_or("");
                    conflict.remoteHash = remoteChange.hash.value_or("");
                    
                    conflicts.push_back(conflict);
                    
                    Logger::warn("CONFLICT detected: " + conflict.path);
                }
            }
        }
    }
    
    Logger::info("Found " + std::to_string(conflicts.size()) + " conflicts");
    
    return conflicts;
}

// Metadata comparison
bool ChangeDetector::hasFileChanged(
    const std::string& path,
    const std::chrono::system_clock::time_point& timestamp,
    const std::string& hash
) {
    (void)timestamp; // TODO: Use when modifiedAt is converted to timestamp
    
    auto metadata = db_->getFileMetadata(path);
    
    if (!metadata) {
        return true;  // File not in DB = changed
    }
    
    // Compare hash (most reliable)
    if (!hash.empty() && metadata->checksum != hash) {
        return true;
    }
    
    // Compare timestamp (less reliable due to timezone issues)
    // Note: modifiedAt is a string, not timestamp - skip this check
    // TODO: Parse modifiedAt string to timestamp for comparison
    
    return false;
}

// Helper: Calculate SHA256 hash
std::string ChangeDetector::calculateFileHash(const std::string& filePath) {
    try {
        std::ifstream file(filePath, std::ios::binary);
        if (!file.is_open()) {
            Logger::error("Cannot open file for hashing: " + filePath);
            return "";
        }
        
        // Simple hash placeholder - TODO: Use proper SHA256 library
        std::stringstream ss;
        ss << std::hex << std::hash<std::string>{}(filePath);
        return ss.str();
        
    } catch (const std::exception& e) {
        Logger::error("Failed to calculate hash: " + 
                                   std::string(e.what()));
        return "";
    }
}

// Helper: Recursive directory scan
void ChangeDetector::scanDirectory(
    const std::string& dirPath,
    const std::string& basePath,
    std::vector<DetectedChange>& changes
) {
    try {
        for (const auto& entry : fs::recursive_directory_iterator(dirPath)) {
            if (!entry.is_regular_file()) continue;
            
            std::string fullPath = entry.path().string();
            std::string relativePath = fullPath.substr(basePath.length());
            
            // Normalize path separators
            std::replace(relativePath.begin(), relativePath.end(), '\\', '/');
            if (relativePath[0] == '/') {
                relativePath = relativePath.substr(1);
            }
            
            // Get file metadata
            auto lastWrite = fs::last_write_time(entry.path());
            auto timestamp = std::chrono::system_clock::now(); // TODO: convert lastWrite
            size_t size = fs::file_size(entry.path());
            std::string hash = calculateFileHash(fullPath);
            
            // Check if file has changed
            auto dbMeta = db_->getFileMetadata(relativePath);
            
            if (!dbMeta) {
                // New file
                DetectedChange change;
                change.path = relativePath;
                change.type = ChangeType::CREATED;
                change.timestamp = timestamp;
                change.hash = hash;
                change.size = size;
                change.isRemote = false;
                changes.push_back(change);
                
                Logger::debug("Local CREATED: " + relativePath);
                
            } else if (dbMeta->checksum != hash || dbMeta->size != size) {
                // Modified file
                DetectedChange change;
                change.path = relativePath;
                change.type = ChangeType::MODIFIED;
                change.timestamp = timestamp;
                change.hash = hash;
                change.size = size;
                change.isRemote = false;
                changes.push_back(change);
                
                Logger::debug("Local MODIFIED: " + relativePath);
            }
        }
    } catch (const std::exception& e) {
        Logger::error("Failed to scan directory: " + 
                                   std::string(e.what()));
    }
}

} // namespace baludesk

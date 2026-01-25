#pragma once

#include <string>
#include <vector>
#include <optional>
#include <nlohmann/json.hpp>

namespace baludesk {

struct FileItem {
    int id;
    std::string name;
    std::string path;
    std::string type; // "file" or "directory"
    int64_t size;
    std::string owner;
    std::string created_at;
    std::string updated_at;
    std::optional<int> mount_id;
};

struct Mountpoint {
    std::string id;
    std::string name;
    std::string mount_path;
    std::string raid_level;
    int64_t total_size;
    int64_t used_size;
    int64_t available_size;
};

struct Permission {
    std::string username;
    bool can_view;
    bool can_edit;
    bool can_delete;
};

class BaluhostClient {
public:
    BaluhostClient(const std::string& baseUrl);
    ~BaluhostClient();

    // Authentication
    bool login(const std::string& username, const std::string& password);
    void setAuthToken(const std::string& token);
    bool isAuthenticated() const;

    // File Operations
    std::vector<FileItem> listFiles(const std::string& path, const std::string& mountId = "");
    std::vector<Mountpoint> getMountpoints();
    bool createFolder(const std::string& path, const std::string& name, const std::string& mountId = "");
    bool renameFile(int fileId, const std::string& newName);
    bool moveFile(int fileId, const std::string& newPath);
    bool deleteFile(int fileId);
    bool downloadFile(int fileId, const std::string& localPath);
    bool downloadFileByPath(const std::string& remotePath, const std::string& localPath);
    bool uploadFile(const std::string& localPath, const std::string& remotePath, const std::string& mountId = "");

    // Permissions
    std::vector<Permission> getPermissions(int fileId);
    bool setPermission(int fileId, const std::string& username, bool canView, bool canEdit, bool canDelete);
    bool removePermission(int fileId, const std::string& username);

    // System Information (from BaluHost server)
    std::optional<nlohmann::json> getSystemInfo();
    std::optional<nlohmann::json> getRaidStatus();
    std::optional<nlohmann::json> getPowerMonitoring();

    // Error handling
    std::string getLastError() const;

    // Get server URL
    std::string getBaseUrl() const;

    // Get authenticated username
    std::string getUsername() const;

private:
    std::string baseUrl_;
    std::string authToken_;
    std::string username_;
    std::string lastError_;

    // HTTP request helpers
    std::optional<nlohmann::json> makeRequest(
        const std::string& method,
        const std::string& endpoint,
        const nlohmann::json& body = nullptr,
        bool requireAuth = true
    );

    std::optional<std::vector<uint8_t>> downloadBinary(const std::string& endpoint);
    bool uploadBinary(const std::string& endpoint, const std::vector<uint8_t>& data, const std::string& filename);

    // JSON parsing helpers
    FileItem parseFileItem(const nlohmann::json& json);
    Mountpoint parseMountpoint(const nlohmann::json& json);
    Permission parsePermission(const nlohmann::json& json);
};

} // namespace baludesk

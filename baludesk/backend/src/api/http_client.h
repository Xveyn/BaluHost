#pragma once

#include <string>
#include <vector>
#include <memory>
#include <functional>
#include <curl/curl.h>

namespace baludesk {

struct RemoteFile {
    std::string name;
    std::string path;
    uint64_t size;
    bool isDirectory;
    std::string modifiedAt;
    std::string hash;  // SHA256 hash for file integrity
};

struct RemoteChange {
    std::string path;
    std::string action; // created, modified, deleted
    std::string timestamp;
};

struct DownloadProgress {
    size_t bytesDownloaded;
    size_t totalBytes;
    double percentage;
};

/**
 * SystemInfoFromServer - System metrics from BaluHost server
 */
struct SystemInfoFromServer {
    double cpuUsage;
    uint32_t cpuCores;
    uint32_t cpuFrequency;
    uint64_t memoryTotal;
    uint64_t memoryUsed;
    uint64_t memoryAvailable;
    uint64_t diskTotal;
    uint64_t diskUsed;
    uint64_t diskAvailable;
    uint64_t uptime;
};

/**
 * Forward declare RaidArray from raid_info.h
 * (included in .cpp to avoid circular dependencies)
 */
struct RaidArray;

/**
 * RaidStatusFromServer - RAID status from BaluHost server
 */
struct RaidStatusFromServer {
    std::vector<RaidArray> arrays;
    bool devMode;
};

/**
 * HttpClient - REST API client for BaluHost NAS
 * 
 * Handles all HTTP communication using libcurl
 */
class HttpClient {
public:
    explicit HttpClient(const std::string& baseUrl);
    ~HttpClient();

    // Authentication
    bool login(const std::string& username, const std::string& password);
    void setAuthToken(const std::string& token);
    void clearAuthToken();
    bool isAuthenticated() const;

    // Device Registration
    bool registerDevice(const std::string& deviceId, const std::string& deviceName);

    // File operations
    virtual std::vector<RemoteFile> listFiles(const std::string& path);
    virtual bool uploadFile(const std::string& localPath, const std::string& remotePath);
    virtual bool downloadFile(const std::string& remotePath, const std::string& localPath);
    virtual bool deleteFile(const std::string& remotePath);
    
    // Advanced download with resume support
    bool downloadFileRange(
        const std::string& remotePath, 
        const std::string& localPath,
        size_t startByte,
        size_t endByte = 0  // 0 = until end
    );
    
    // Download with progress callback
    using ProgressCallback = std::function<void(const DownloadProgress&)>;
    bool downloadFileWithProgress(
        const std::string& remotePath,
        const std::string& localPath,
        ProgressCallback callback
    );

    // Sync operations
    std::vector<RemoteChange> getChangesSince(const std::string& timestamp);

    // System information from BaluHost server
    SystemInfoFromServer getSystemInfoFromServer();
    RaidStatusFromServer getRaidStatusFromServer();

    // Configuration
    void setTimeout(long timeoutSeconds);
    void setVerbose(bool verbose);

    // Convenience GET helper returning raw response body
    std::string get(const std::string& path);

private:
    std::string performRequest(const std::string& url, const std::string& method,
                               const std::string& body = "");
    static size_t writeCallback(void* contents, size_t size, size_t nmemb, void* userp);
    static size_t readCallback(void* ptr, size_t size, size_t nmemb, void* userp);
    static size_t writeFileCallback(void* contents, size_t size, size_t nmemb, void* userp);
    static int progressCallback(void* clientp, curl_off_t dltotal, curl_off_t dlnow,
                               curl_off_t ultotal, curl_off_t ulnow);

    std::string baseUrl_;
    std::string authToken_;
    CURL* curl_;
    long timeout_;
    bool verbose_;
};

} // namespace baludesk

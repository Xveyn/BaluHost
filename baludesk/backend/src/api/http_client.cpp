#include "http_client.h"
#include "../utils/logger.h"
#include "../utils/raid_info.h"
#include <fstream>
#include <sstream>
#include <curl/curl.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace baludesk {

// ============================================================================
// Helper Structures
// ============================================================================

struct WriteCallbackData {
    std::string* buffer;
};

struct ReadCallbackData {
    std::ifstream* file;
};

// ============================================================================
// HttpClient Implementation
// ============================================================================

HttpClient::HttpClient(const std::string& baseUrl) 
    : baseUrl_(baseUrl), curl_(nullptr), timeout_(30), verbose_(false) {
    curl_global_init(CURL_GLOBAL_DEFAULT);
    curl_ = curl_easy_init();
    
    if (!curl_) {
        Logger::critical("Failed to initialize libcurl");
        throw std::runtime_error("Failed to initialize libcurl");
    }
    // Ensure local requests bypass any system proxy settings (important on Windows)
    // so that calls to 127.0.0.1 or localhost do not try to use an external proxy.
    try {
        const char* noProxy = "127.0.0.1;localhost";
        curl_easy_setopt(curl_, CURLOPT_NOPROXY, noProxy);
    } catch (...) {
        // Non-fatal: continue without nopxy if setting fails
    }
    // Disable any proxy explicitly for this handle. Verbose logging
    // is controlled by `verbose_` and set per-request when enabled.
    try {
        curl_easy_setopt(curl_, CURLOPT_PROXY, "");
    } catch (...) {
    }
}

HttpClient::~HttpClient() {
    if (curl_) {
        curl_easy_cleanup(curl_);
    }
    curl_global_cleanup();
}

// ============================================================================
// Authentication
// ============================================================================

bool HttpClient::login(const std::string& username, const std::string& password) {
    Logger::info("Attempting login for user: {}", username);
    
    try {
        json requestBody = {
            {"username", username},
            {"password", password}
        };
        
        std::string response = performRequest(
            baseUrl_ + "/api/auth/login",
            "POST",
            requestBody.dump()
        );
        
        auto responseJson = json::parse(response);
        
        if (responseJson.contains("access_token")) {
            authToken_ = responseJson["access_token"].get<std::string>();
            Logger::info("Login successful, token acquired");
            return true;
        }
        
        Logger::error("Login failed: No access token in response");
        return false;
        
    } catch (const std::exception& e) {
        Logger::error("Login failed: {}", e.what());
        return false;
    }
}

void HttpClient::setAuthToken(const std::string& token) {
    authToken_ = token;
    Logger::debug("Auth token updated");
}

void HttpClient::clearAuthToken() {
    authToken_.clear();
    Logger::debug("Auth token cleared");
}

bool HttpClient::isAuthenticated() const {
    return !authToken_.empty();
}

bool HttpClient::registerDevice(const std::string& deviceId, const std::string& deviceName) {
    Logger::info("Registering desktop device: {} ({})", deviceName, deviceId);

    if (!isAuthenticated()) {
        Logger::error("Cannot register device: Not authenticated");
        return false;
    }

    try {
        json requestBody = {
            {"device_id", deviceId},
            {"device_name", deviceName}
        };

        std::string response = performRequest(
            baseUrl_ + "/api/sync/register-desktop",
            "POST",
            requestBody.dump()
        );

        auto responseJson = json::parse(response);

        if (responseJson.contains("device_id")) {
            std::string status = responseJson.value("status", "");
            if (status == "registered") {
                Logger::info("Device registered successfully");
            } else if (status == "already_registered") {
                Logger::info("Device already registered (re-registration successful)");
            } else {
                Logger::info("Device registration response: {}", status);
            }
            return true;
        }

        Logger::error("Device registration failed: No device_id in response");
        return false;

    } catch (const std::exception& e) {
        Logger::error("Device registration failed: {}", e.what());
        return false;
    }
}

// ============================================================================
// File Operations
// ============================================================================

std::vector<RemoteFile> HttpClient::listFiles(const std::string& remotePath) {
    Logger::debug("Listing files: {}", remotePath);
    
    std::vector<RemoteFile> files;
    
    try {
        std::string url = baseUrl_ + "/api/files?path=" + 
                         curl_easy_escape(curl_, remotePath.c_str(), static_cast<int>(remotePath.length()));
        
        std::string response = performRequest(url, "GET");
        auto responseJson = json::parse(response);
        
        if (responseJson.contains("files") && responseJson["files"].is_array()) {
            for (const auto& fileJson : responseJson["files"]) {
                RemoteFile file;
                file.name = fileJson.value("name", "");
                file.path = fileJson.value("path", "");
                file.size = fileJson.value("size", 0);
                file.isDirectory = fileJson.value("is_directory", false);
                file.modifiedAt = fileJson.value("modified_at", "");
                files.push_back(file);
            }
        }
        
        Logger::debug("Listed {} files/directories", files.size());
        
    } catch (const std::exception& e) {
        Logger::error("Failed to list files: {}", e.what());
    }
    
    return files;
}

bool HttpClient::uploadFile(const std::string& localPath, const std::string& remotePath) {
    Logger::info("Uploading: {} -> {}", localPath, remotePath);
    
    if (!isAuthenticated()) {
        Logger::error("Cannot upload: Not authenticated");
        return false;
    }
    
    std::ifstream file(localPath, std::ios::binary);
    if (!file) {
        Logger::error("Cannot open file: {}", localPath);
        return false;
    }
    
    // Get file size
    file.seekg(0, std::ios::end);
    size_t fileSize = file.tellg();
    file.seekg(0, std::ios::beg);
    
    try {
        CURL* uploadCurl = curl_easy_init();
        if (!uploadCurl) {
            Logger::error("Failed to create upload handle");
            return false;
        }
        // Bypass proxy for local addresses to avoid proxy interference
        curl_easy_setopt(uploadCurl, CURLOPT_NOPROXY, "127.0.0.1;localhost");
        curl_easy_setopt(uploadCurl, CURLOPT_PROXY, "");
        if (verbose_) {
            curl_easy_setopt(uploadCurl, CURLOPT_VERBOSE, 1L);
        }
        
        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "Content-Type: application/octet-stream");
        std::string authHeader = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, authHeader.c_str());
        
        std::string url = baseUrl_ + "/api/files/upload?path=" + 
                         curl_easy_escape(uploadCurl, remotePath.c_str(), static_cast<int>(remotePath.length()));
        
        ReadCallbackData callbackData{&file};
        std::string responseBuffer;
        
        curl_easy_setopt(uploadCurl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(uploadCurl, CURLOPT_UPLOAD, 1L);
        curl_easy_setopt(uploadCurl, CURLOPT_READFUNCTION, readCallback);
        curl_easy_setopt(uploadCurl, CURLOPT_READDATA, &callbackData);
        curl_easy_setopt(uploadCurl, CURLOPT_INFILESIZE_LARGE, (curl_off_t)fileSize);
        curl_easy_setopt(uploadCurl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(uploadCurl, CURLOPT_WRITEFUNCTION, writeCallback);
        curl_easy_setopt(uploadCurl, CURLOPT_WRITEDATA, &responseBuffer);
        curl_easy_setopt(uploadCurl, CURLOPT_TIMEOUT, timeout_);
        
        if (verbose_) {
            curl_easy_setopt(uploadCurl, CURLOPT_VERBOSE, 1L);
        }
        
        CURLcode res = curl_easy_perform(uploadCurl);
        
        long httpCode = 0;
        curl_easy_getinfo(uploadCurl, CURLINFO_RESPONSE_CODE, &httpCode);
        
        curl_slist_free_all(headers);
        curl_easy_cleanup(uploadCurl);
        
        if (res != CURLE_OK) {
            Logger::error("Upload failed: {}", curl_easy_strerror(res));
            return false;
        }
        
        if (httpCode >= 200 && httpCode < 300) {
            Logger::info("Upload successful (HTTP {})", httpCode);
            return true;
        } else {
            Logger::error("Upload failed with HTTP {}: {}", httpCode, responseBuffer);
            return false;
        }
        
    } catch (const std::exception& e) {
        Logger::error("Upload exception: {}", e.what());
        return false;
    }
}

bool HttpClient::downloadFile(const std::string& remotePath, const std::string& localPath) {
    Logger::info("Downloading: {} -> {}", remotePath, localPath);
    
    if (!isAuthenticated()) {
        Logger::error("Cannot download: Not authenticated");
        return false;
    }
    
    std::ofstream outFile(localPath, std::ios::binary);
    if (!outFile) {
        Logger::error("Cannot create file: {}", localPath);
        return false;
    }
    
    try {
        CURL* downloadCurl = curl_easy_init();
        if (!downloadCurl) {
            Logger::error("Failed to create download handle");
            return false;
        }
        // Bypass proxy for local addresses to avoid proxy interference
        curl_easy_setopt(downloadCurl, CURLOPT_NOPROXY, "127.0.0.1;localhost");
        curl_easy_setopt(downloadCurl, CURLOPT_PROXY, "");
        if (verbose_) {
            curl_easy_setopt(downloadCurl, CURLOPT_VERBOSE, 1L);
        }
        // Bypass proxy for local addresses to avoid proxy interference
        curl_easy_setopt(downloadCurl, CURLOPT_NOPROXY, "127.0.0.1;localhost");
        
        struct curl_slist* headers = nullptr;
        std::string authHeader = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, authHeader.c_str());
        
        std::string url = baseUrl_ + "/api/files/download?path=" + 
                         curl_easy_escape(downloadCurl, remotePath.c_str(), static_cast<int>(remotePath.length()));
        
        curl_easy_setopt(downloadCurl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(downloadCurl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(downloadCurl, CURLOPT_WRITEFUNCTION, writeCallback);
        
        WriteCallbackData callbackData{};
        std::string fileContent;
        callbackData.buffer = &fileContent;
        
        curl_easy_setopt(downloadCurl, CURLOPT_WRITEDATA, &callbackData);
        curl_easy_setopt(downloadCurl, CURLOPT_TIMEOUT, timeout_);
        
        if (verbose_) {
            curl_easy_setopt(downloadCurl, CURLOPT_VERBOSE, 1L);
        }
        
        CURLcode res = curl_easy_perform(downloadCurl);
        
        long httpCode = 0;
        curl_easy_getinfo(downloadCurl, CURLINFO_RESPONSE_CODE, &httpCode);
        
        curl_slist_free_all(headers);
        curl_easy_cleanup(downloadCurl);
        
        if (res != CURLE_OK) {
            Logger::error("Download failed: {}", curl_easy_strerror(res));
            return false;
        }
        
        if (httpCode >= 200 && httpCode < 300) {
            outFile.write(fileContent.data(), fileContent.size());
            outFile.close();
            Logger::info("Download successful ({} bytes)", fileContent.size());
            return true;
        } else {
            Logger::error("Download failed with HTTP {}", httpCode);
            return false;
        }
        
    } catch (const std::exception& e) {
        Logger::error("Download exception: {}", e.what());
        return false;
    }
}

bool HttpClient::deleteFile(const std::string& remotePath) {
    Logger::info("Deleting remote file: {}", remotePath);
    
    try {
        std::string url = baseUrl_ + "/api/files?path=" + 
                         curl_easy_escape(curl_, remotePath.c_str(), static_cast<int>(remotePath.length()));
        
        std::string response = performRequest(url, "DELETE");
        
        Logger::info("Delete successful");
        return true;
        
    } catch (const std::exception& e) {
        Logger::error("Delete failed: {}", e.what());
        return false;
    }
}

// ============================================================================
// Sync Operations
// ============================================================================

std::vector<RemoteChange> HttpClient::getChangesSince(const std::string& timestamp) {
    Logger::debug("Getting changes since: {}", timestamp);
    
    std::vector<RemoteChange> changes;
    
    try {
        std::string url = baseUrl_ + "/api/sync/changes?since=" + 
                         curl_easy_escape(curl_, timestamp.c_str(), static_cast<int>(timestamp.length()));
        
        std::string response = performRequest(url, "GET");
        auto responseJson = json::parse(response);
        
        if (responseJson.contains("changes") && responseJson["changes"].is_array()) {
            for (const auto& changeJson : responseJson["changes"]) {
                RemoteChange change;
                change.path = changeJson.value("path", "");
                change.action = changeJson.value("action", "");
                change.timestamp = changeJson.value("timestamp", "");
                changes.push_back(change);
            }
        }
        
        Logger::debug("Retrieved {} changes", changes.size());
        
    } catch (const std::exception& e) {
        Logger::error("Failed to get changes: {}", e.what());
    }
    
    return changes;
}

// ============================================================================
// Configuration
// ============================================================================

void HttpClient::setTimeout(long timeout) {
    timeout_ = timeout;
    Logger::debug("Timeout set to {} seconds", timeout);
}

void HttpClient::setVerbose(bool verbose) {
    verbose_ = verbose;
    Logger::debug("Verbose mode: {}", verbose ? "enabled" : "disabled");
}

// ============================================================================
// Private Methods
// ============================================================================

std::string HttpClient::performRequest(const std::string& url, const std::string& method, const std::string& body) {
    if (!curl_) {
        throw std::runtime_error("CURL not initialized");
    }
    
    std::string responseBuffer;
    WriteCallbackData callbackData{&responseBuffer};
    
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    
    if (isAuthenticated()) {
        std::string authHeader = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, authHeader.c_str());
    }
    
    curl_easy_setopt(curl_, CURLOPT_URL, url.c_str());
    Logger::debug("HTTP request: {} {}", method, url);
    curl_easy_setopt(curl_, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl_, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl_, CURLOPT_WRITEDATA, &callbackData);
    curl_easy_setopt(curl_, CURLOPT_TIMEOUT, timeout_);
    
    if (verbose_) {
        curl_easy_setopt(curl_, CURLOPT_VERBOSE, 1L);
    }
    
    if (method == "POST") {
        curl_easy_setopt(curl_, CURLOPT_POST, 1L);
        curl_easy_setopt(curl_, CURLOPT_POSTFIELDS, body.c_str());
    } else if (method == "DELETE") {
        curl_easy_setopt(curl_, CURLOPT_CUSTOMREQUEST, "DELETE");
    } else if (method == "PUT") {
        curl_easy_setopt(curl_, CURLOPT_CUSTOMREQUEST, "PUT");
        curl_easy_setopt(curl_, CURLOPT_POSTFIELDS, body.c_str());
    } else {
        // Default is GET
        curl_easy_setopt(curl_, CURLOPT_HTTPGET, 1L);
    }
    
    CURLcode res = curl_easy_perform(curl_);
    
    long httpCode = 0;
    curl_easy_getinfo(curl_, CURLINFO_RESPONSE_CODE, &httpCode);
    
    curl_slist_free_all(headers);
    
    if (res != CURLE_OK) {
        std::string error = "CURL error: " + std::string(curl_easy_strerror(res));
        Logger::error(error);
        throw std::runtime_error(error);
    }
    
    if (httpCode >= 400) {
        std::string error = "HTTP error " + std::to_string(httpCode) + ": " + responseBuffer;
        Logger::error(error);
        throw std::runtime_error(error);
    }
    
    return responseBuffer;
}

size_t HttpClient::writeCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t totalSize = size * nmemb;
    auto* data = static_cast<WriteCallbackData*>(userp);
    
    if (data && data->buffer) {
        data->buffer->append(static_cast<char*>(contents), totalSize);
    }
    
    return totalSize;
}

size_t HttpClient::readCallback(void* ptr, size_t size, size_t nmemb, void* userp) {
    size_t maxSize = size * nmemb;
    auto* data = static_cast<ReadCallbackData*>(userp);
    
    if (data && data->file && data->file->good()) {
        data->file->read(static_cast<char*>(ptr), maxSize);
        return data->file->gcount();
    }
    
    return 0;
}

// Write callback for file downloads
size_t HttpClient::writeFileCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t totalSize = size * nmemb;
    auto* file = static_cast<std::ofstream*>(userp);
    
    if (file && file->is_open()) {
        file->write(static_cast<char*>(contents), totalSize);
        return totalSize;
    }
    
    return 0;
}

// Progress callback
int HttpClient::progressCallback(void* clientp, curl_off_t dltotal, curl_off_t dlnow,
                                curl_off_t ultotal, curl_off_t ulnow) {
    (void)ultotal;  // Intentionally unused
    (void)ulnow;    // Intentionally unused
    auto* callback = static_cast<ProgressCallback*>(clientp);
    
    if (callback && dltotal > 0) {
        DownloadProgress progress;
        progress.bytesDownloaded = static_cast<size_t>(dlnow);
        progress.totalBytes = static_cast<size_t>(dltotal);
        progress.percentage = (static_cast<double>(dlnow) / static_cast<double>(dltotal)) * 100.0;
        
        (*callback)(progress);
    }
    
    return 0;  // Return 0 to continue, non-zero to abort
}

// Download file with Range support (resume capability)
bool HttpClient::downloadFileRange(
    const std::string& remotePath,
    const std::string& localPath,
    size_t startByte,
    size_t endByte
) {
    Logger::info("Downloading file range: {} (bytes {}-{})", remotePath, startByte, 
                endByte > 0 ? std::to_string(endByte) : "end");
    
    try {
        std::ofstream file(localPath, std::ios::binary | std::ios::app);
        if (!file.is_open()) {
            Logger::error("Cannot open file for writing: {}", localPath);
            return false;
        }
        
        CURL* downloadCurl = curl_easy_init();
        if (!downloadCurl) {
            Logger::error("Failed to create download handle");
            return false;
        }
        // Bypass proxy for local addresses to avoid proxy interference
        curl_easy_setopt(downloadCurl, CURLOPT_NOPROXY, "127.0.0.1;localhost");
        
        struct curl_slist* headers = nullptr;
        std::string authHeader = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, authHeader.c_str());
        
        // Set Range header for resume
        std::string rangeHeader = "Range: bytes=" + std::to_string(startByte) + "-";
        if (endByte > 0) {
            rangeHeader += std::to_string(endByte);
        }
        headers = curl_slist_append(headers, rangeHeader.c_str());
        
        std::string url = baseUrl_ + "/api/files/download?path=" + 
                         curl_easy_escape(downloadCurl, remotePath.c_str(), static_cast<int>(remotePath.length()));
        
        curl_easy_setopt(downloadCurl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(downloadCurl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(downloadCurl, CURLOPT_WRITEFUNCTION, writeFileCallback);
        curl_easy_setopt(downloadCurl, CURLOPT_WRITEDATA, &file);
        curl_easy_setopt(downloadCurl, CURLOPT_TIMEOUT, timeout_);
        curl_easy_setopt(downloadCurl, CURLOPT_FOLLOWLOCATION, 1L);
        
        if (verbose_) {
            curl_easy_setopt(downloadCurl, CURLOPT_VERBOSE, 1L);
        }
        
        CURLcode res = curl_easy_perform(downloadCurl);
        
        long httpCode = 0;
        curl_easy_getinfo(downloadCurl, CURLINFO_RESPONSE_CODE, &httpCode);
        
        curl_slist_free_all(headers);
        curl_easy_cleanup(downloadCurl);
        file.close();
        
        if (res != CURLE_OK) {
            Logger::error("Download range failed: {}", curl_easy_strerror(res));
            return false;
        }
        
        // Accept both 200 (full content) and 206 (partial content)
        if (httpCode == 200 || httpCode == 206) {
            Logger::info("Download range successful (HTTP {})", httpCode);
            return true;
        } else {
            Logger::error("Download range failed with HTTP {}", httpCode);
            return false;
        }
        
    } catch (const std::exception& e) {
        Logger::error("Exception during download range: {}", e.what());
        return false;
    }
}

// Simple GET helper
std::string HttpClient::get(const std::string& path) {
    // path may be absolute (full URL) or relative path starting with '/'
    std::string url;
    if (path.rfind("http://", 0) == 0 || path.rfind("https://", 0) == 0) {
        url = path;
    } else {
        url = baseUrl_ + path;
    }
    return performRequest(url, "GET");
}

// Download with progress callback
bool HttpClient::downloadFileWithProgress(
    const std::string& remotePath,
    const std::string& localPath,
    ProgressCallback callback
) {
    Logger::info("Downloading file with progress: {}", remotePath);
    
    try {
        std::ofstream file(localPath, std::ios::binary);
        if (!file.is_open()) {
            Logger::error("Cannot open file for writing: {}", localPath);
            return false;
        }
        
        CURL* downloadCurl = curl_easy_init();
        if (!downloadCurl) {
            Logger::error("Failed to create download handle");
            return false;
        }
        
        struct curl_slist* headers = nullptr;
        std::string authHeader = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, authHeader.c_str());
        
        std::string url = baseUrl_ + "/api/files/download?path=" + 
                         curl_easy_escape(downloadCurl, remotePath.c_str(), static_cast<int>(remotePath.length()));
        
        curl_easy_setopt(downloadCurl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(downloadCurl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(downloadCurl, CURLOPT_WRITEFUNCTION, writeFileCallback);
        curl_easy_setopt(downloadCurl, CURLOPT_WRITEDATA, &file);
        curl_easy_setopt(downloadCurl, CURLOPT_TIMEOUT, timeout_);
        curl_easy_setopt(downloadCurl, CURLOPT_FOLLOWLOCATION, 1L);
        
        // Enable progress callback
        curl_easy_setopt(downloadCurl, CURLOPT_XFERINFOFUNCTION, progressCallback);
        curl_easy_setopt(downloadCurl, CURLOPT_XFERINFODATA, &callback);
        curl_easy_setopt(downloadCurl, CURLOPT_NOPROGRESS, 0L);
        
        if (verbose_) {
            curl_easy_setopt(downloadCurl, CURLOPT_VERBOSE, 1L);
        }
        
        CURLcode res = curl_easy_perform(downloadCurl);
        
        long httpCode = 0;
        curl_easy_getinfo(downloadCurl, CURLINFO_RESPONSE_CODE, &httpCode);
        
        curl_slist_free_all(headers);
        curl_easy_cleanup(downloadCurl);
        file.close();
        
        if (res != CURLE_OK) {
            Logger::error("Download with progress failed: {}", curl_easy_strerror(res));
            return false;
        }
        
        if (httpCode >= 200 && httpCode < 300) {
            Logger::info("Download with progress successful (HTTP {})", httpCode);
            return true;
        } else {
            Logger::error("Download with progress failed with HTTP {}", httpCode);
            return false;
        }
        
    } catch (const std::exception& e) {
        Logger::error("Exception during download with progress: {}", e.what());
        return false;
    }
}

// ============================================================================
// System Info from BaluHost Server
// ============================================================================

SystemInfoFromServer HttpClient::getSystemInfoFromServer() {
    Logger::debug("Fetching system info from BaluHost server");

    try {
        std::string response = get("/api/system/info");
        auto json = nlohmann::json::parse(response);

        SystemInfoFromServer info;
        info.cpuUsage = json["cpu"]["usage"].get<double>();
        info.cpuCores = json["cpu"]["cores"].get<uint32_t>();
        info.cpuFrequency = json["cpu"]["frequency_mhz"].get<uint32_t>();
        info.memoryTotal = json["memory"]["total"].get<uint64_t>();
        info.memoryUsed = json["memory"]["used"].get<uint64_t>();
        info.memoryAvailable = json["memory"]["available"].get<uint64_t>();
        info.diskTotal = json["disk"]["total"].get<uint64_t>();
        info.diskUsed = json["disk"]["used"].get<uint64_t>();
        info.diskAvailable = json["disk"]["available"].get<uint64_t>();
        info.uptime = json["uptime"].get<uint64_t>();

        Logger::debug("System info fetched successfully from server");
        return info;
    } catch (const std::exception& e) {
        Logger::error("Failed to fetch system info from server: {}", e.what());
        throw;
    }
}

RaidStatusFromServer HttpClient::getRaidStatusFromServer() {
    Logger::debug("Fetching RAID status from BaluHost server");

    try {
        std::string response = get("/api/system/raid/status");
        auto json = nlohmann::json::parse(response);

        RaidStatusFromServer status;
        status.devMode = json.value("dev_mode", false);

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

                status.arrays.push_back(array);
            }
        }

        Logger::debug("RAID status fetched successfully from server ({} arrays)",
                     status.arrays.size());
        return status;
    } catch (const std::exception& e) {
        Logger::error("Failed to fetch RAID status from server: {}", e.what());
        throw;
    }
}

} // namespace baludesk


#pragma once

#include "file_watcher_v2.h"
#include <windows.h>
#include <map>
#include <thread>
#include <atomic>
#include <vector>

namespace baludesk {

/**
 * @brief Windows FileWatcher using ReadDirectoryChangesW
 * 
 * Implementation details:
 * - OVERLAPPED I/O for async operation
 * - Recursive directory watching
 * - FILE_NOTIFY_INFORMATION parsing
 * - Proper Unicode (wide char) handling
 */
class WindowsFileWatcher : public IFileWatcherImpl {
public:
    WindowsFileWatcher();
    ~WindowsFileWatcher() override;

    bool startWatch(const std::string& path) override;
    void stopWatch(const std::string& path) override;
    void stopAll() override;
    bool isWatching(const std::string& path) const override;
    void setCallback(std::function<void(const FileEvent&)> callback) override;

private:
    struct WatchContext {
        std::string path;
        HANDLE dirHandle;
        HANDLE stopEvent;
        std::thread watchThread;
        std::atomic<bool> running;
        std::vector<BYTE> buffer;  // FILE_NOTIFY_INFORMATION buffer
        OVERLAPPED overlapped;
        
        WatchContext() : dirHandle(INVALID_HANDLE_VALUE), 
                        stopEvent(INVALID_HANDLE_VALUE),
                        running(false),
                        buffer(64 * 1024) {  // 64KB buffer
            ZeroMemory(&overlapped, sizeof(OVERLAPPED));
        }
    };

    /**
     * @brief Watch thread entry point
     */
    void watchThreadFunc(WatchContext* ctx);

    /**
     * @brief Process FILE_NOTIFY_INFORMATION structure
     */
    void processNotifications(WatchContext* ctx, DWORD bytesReturned);

    /**
     * @brief Convert Windows action to FileAction
     */
    FileAction convertAction(DWORD action);

    /**
     * @brief Convert wide string to UTF-8
     */
    std::string wideToUtf8(const std::wstring& wide);

    std::map<std::string, std::unique_ptr<WatchContext>> watches_;
    std::function<void(const FileEvent&)> callback_;
    mutable std::mutex mutex_;
};

} // namespace baludesk

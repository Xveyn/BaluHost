#pragma once

#include "sync_engine.h"
#include <string>
#include <functional>

namespace baludesk {

// Forward declarations
class FileWatcher {
public:
    FileWatcher();
    ~FileWatcher();

    void watch(const std::string& path);
    void unwatch(const std::string& path);
    void stop();
    void setCallback(std::function<void(const FileEvent&)> callback);

private:
    std::function<void(const FileEvent&)> callback_;
};

} // namespace baludesk

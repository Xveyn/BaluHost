#pragma once

namespace baludesk {

// Forward declaration
class SyncEngine;

class IpcServer {
public:
    explicit IpcServer(SyncEngine* engine);
    
    bool start();
    void stop();
    void processMessages();

private:
    SyncEngine* engine_;
};

} // namespace baludesk

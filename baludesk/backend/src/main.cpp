#include "sync/sync_engine.h"
#include "ipc/ipc_server.h"
#include "utils/logger.h"
#include "utils/config.h"
#include <iostream>
#include <csignal>
#include <atomic>

using namespace baludesk;

std::atomic<bool> running{true};

void signalHandler(int signal) {
    if (signal == SIGINT || signal == SIGTERM) {
        Logger::info("Received shutdown signal");
        running = false;
    }
}

int main(int argc, char* argv[]) {
    // Parse command line arguments
    std::string configPath = "config.json";
    bool verbose = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--config" && i + 1 < argc) {
            configPath = argv[++i];
        } else if (arg == "--verbose" || arg == "-v") {
            verbose = true;
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "BaluDesk Backend\n"
                      << "Usage: baludesk-backend [options]\n"
                      << "Options:\n"
                      << "  --config <path>  Configuration file path (default: config.json)\n"
                      << "  --verbose, -v    Enable verbose logging\n"
                      << "  --help, -h       Show this help message\n";
            return 0;
        }
    }

    // Initialize logger
    Logger::initialize("baludesk.log", verbose);
    Logger::info("=== BaluDesk Backend Starting ===");

    // Load configuration
    Config config;
    if (!config.load(configPath)) {
        Logger::warn("Config file not found, using defaults");
    }

    // Install signal handlers
    std::signal(SIGINT, signalHandler);
    std::signal(SIGTERM, signalHandler);

    try {
        // Initialize sync engine
        SyncEngine syncEngine;
        if (!syncEngine.initialize(config.getDatabasePath(), config.getServerUrl())) {
            Logger::critical("Failed to initialize SyncEngine");
            return 1;
        }

        // Initialize IPC server for communication with Electron
        IpcServer ipcServer(&syncEngine);
        if (!ipcServer.start()) {
            Logger::critical("Failed to start IPC server");
            return 1;
        }

        // Start the sync engine loop so it can emit status updates
        if (!syncEngine.isRunning()) {
            syncEngine.start();
        }

        Logger::info("BaluDesk Backend initialized successfully");
        Logger::info("Server URL: " + config.getServerUrl());
        Logger::info("Listening for IPC commands on stdin/stdout");

        // Main loop - process IPC messages
        while (running) {
            ipcServer.processMessages();
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        // Cleanup
        Logger::info("Shutting down...");
        ipcServer.stop();
        syncEngine.stop();

    } catch (const std::exception& e) {
        Logger::critical("Fatal error: " + std::string(e.what()));
        return 1;
    }

    Logger::info("=== BaluDesk Backend Stopped ===");
    Logger::shutdown();
    return 0;
}

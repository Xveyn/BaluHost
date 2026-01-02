#pragma once

#include <string>
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/rotating_file_sink.h>

namespace baludesk {

/**
 * Logger - Centralized logging using spdlog
 */
class Logger {
public:
    static void initialize(const std::string& logFile, bool verbose = false);
    static void shutdown();

    static void trace(const std::string& message);
    static void debug(const std::string& message);
    static void info(const std::string& message);
    static void warn(const std::string& message);
    static void error(const std::string& message);
    static void critical(const std::string& message);

private:
    static std::shared_ptr<spdlog::logger> logger_;
};

} // namespace baludesk

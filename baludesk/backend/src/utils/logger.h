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

    // Simple string logging
    static void trace(const std::string& message);
    static void debug(const std::string& message);
    static void info(const std::string& message);
    static void warn(const std::string& message);
    static void error(const std::string& message);
    static void critical(const std::string& message);
    
    // Format string logging (variadic templates)
    template<typename... Args>
    static void trace(const std::string& format, Args&&... args) {
        if (logger_) logger_->trace(format, std::forward<Args>(args)...);
    }
    
    template<typename... Args>
    static void debug(const std::string& format, Args&&... args) {
        if (logger_) logger_->debug(format, std::forward<Args>(args)...);
    }
    
    template<typename... Args>
    static void info(const std::string& format, Args&&... args) {
        if (logger_) logger_->info(format, std::forward<Args>(args)...);
    }
    
    template<typename... Args>
    static void warn(const std::string& format, Args&&... args) {
        if (logger_) logger_->warn(format, std::forward<Args>(args)...);
    }
    
    template<typename... Args>
    static void error(const std::string& format, Args&&... args) {
        if (logger_) logger_->error(format, std::forward<Args>(args)...);
    }
    
    template<typename... Args>
    static void critical(const std::string& format, Args&&... args) {
        if (logger_) logger_->critical(format, std::forward<Args>(args)...);
    }

private:
    static std::shared_ptr<spdlog::logger> logger_;
};

} // namespace baludesk


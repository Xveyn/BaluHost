#include "utils/logger.h"
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/sinks/rotating_file_sink.h>

namespace baludesk {

std::shared_ptr<spdlog::logger> Logger::logger_;

void Logger::initialize(const std::string& logFile, bool verbose) {
    try {
        // Create console sink
        auto console_sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
        console_sink->set_level(verbose ? spdlog::level::debug : spdlog::level::info);

        // Create rotating file sink (5MB max, 3 files)
        auto file_sink = std::make_shared<spdlog::sinks::rotating_file_sink_mt>(
            logFile, 1024 * 1024 * 5, 3);
        file_sink->set_level(spdlog::level::trace);

        // Combine sinks
        std::vector<spdlog::sink_ptr> sinks {console_sink, file_sink};
        logger_ = std::make_shared<spdlog::logger>("baludesk", sinks.begin(), sinks.end());
        logger_->set_level(spdlog::level::trace);
        logger_->flush_on(spdlog::level::error);

        spdlog::register_logger(logger_);
        spdlog::set_default_logger(logger_);

        info("Logger initialized");
    } catch (const spdlog::spdlog_ex& ex) {
        std::cerr << "Logger initialization failed: " << ex.what() << std::endl;
    }
}

void Logger::shutdown() {
    if (logger_) {
        logger_->flush();
        spdlog::shutdown();
    }
}

void Logger::trace(const std::string& message) {
    if (logger_) logger_->trace(message);
}

void Logger::debug(const std::string& message) {
    if (logger_) logger_->debug(message);
}

void Logger::info(const std::string& message) {
    if (logger_) logger_->info(message);
}

void Logger::warn(const std::string& message) {
    if (logger_) logger_->warn(message);
}

void Logger::error(const std::string& message) {
    if (logger_) logger_->error(message);
}

void Logger::critical(const std::string& message) {
    if (logger_) logger_->critical(message);
}

} // namespace baludesk

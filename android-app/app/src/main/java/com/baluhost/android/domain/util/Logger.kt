package com.baluhost.android.domain.util

/**
 * Logging abstraction for domain layer.
 *
 * Provides logging capabilities without Android dependencies.
 * Allows domain layer to remain pure Kotlin and testable without Android framework.
 */
interface Logger {

    /**
     * Log debug message.
     *
     * @param tag Tag for log message (usually class name)
     * @param message Message to log
     */
    fun debug(tag: String, message: String)

    /**
     * Log info message.
     *
     * @param tag Tag for log message
     * @param message Message to log
     */
    fun info(tag: String, message: String)

    /**
     * Log warning message.
     *
     * @param tag Tag for log message
     * @param message Message to log
     */
    fun warn(tag: String, message: String)

    /**
     * Log warning message with throwable.
     *
     * @param tag Tag for log message
     * @param message Message to log
     * @param throwable Exception to log
     */
    fun warn(tag: String, message: String, throwable: Throwable)

    /**
     * Log error message.
     *
     * @param tag Tag for log message
     * @param message Message to log
     */
    fun error(tag: String, message: String)

    /**
     * Log error message with throwable.
     *
     * @param tag Tag for log message
     * @param message Message to log
     * @param throwable Exception to log
     */
    fun error(tag: String, message: String, throwable: Throwable)
}

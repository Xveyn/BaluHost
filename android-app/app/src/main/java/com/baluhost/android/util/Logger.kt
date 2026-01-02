package com.baluhost.android.util

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileWriter
import java.io.PrintWriter
import java.text.SimpleDateFormat
import java.util.*

object Logger {
    private const val TAG = "BaluHost"
    private var logFile: File? = null
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)

    fun init(context: Context) {
        try {
            val dir = File(context.filesDir, "logs")
            if (!dir.exists()) dir.mkdirs()
            logFile = File(dir, "app.log")
        } catch (e: Exception) {
            Log.e(TAG, "Logger init failed: ${e.message}")
        }
    }

    private fun writeToFile(level: String, tag: String, message: String) {
        try {
            val f = logFile ?: return
            val ts = dateFormat.format(Date())
            FileWriter(f, true).use { fw ->
                PrintWriter(fw).use { pw ->
                    pw.println("$ts [$level] $tag: $message")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to write log file: ${e.message}")
        }
    }

    fun d(tag: String, message: String) {
        Log.d(tag, message)
        writeToFile("D", tag, message)
    }

    fun i(tag: String, message: String) {
        Log.i(tag, message)
        writeToFile("I", tag, message)
    }

    fun w(tag: String, message: String) {
        Log.w(tag, message)
        writeToFile("W", tag, message)
    }

    fun e(tag: String, message: String, t: Throwable? = null) {
        Log.e(tag, message, t)
        writeToFile("E", tag, message + (t?.let { " - ${it.message}" } ?: ""))
    }
}

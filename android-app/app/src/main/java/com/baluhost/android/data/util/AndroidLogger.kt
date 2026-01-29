package com.baluhost.android.data.util

import android.util.Log
import com.baluhost.android.domain.util.Logger
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Android implementation of Logger using android.util.Log.
 *
 * Provides logging capabilities for the entire application.
 */
@Singleton
class AndroidLogger @Inject constructor() : Logger {

    override fun debug(tag: String, message: String) {
        Log.d(tag, message)
    }

    override fun info(tag: String, message: String) {
        Log.i(tag, message)
    }

    override fun warn(tag: String, message: String) {
        Log.w(tag, message)
    }

    override fun warn(tag: String, message: String, throwable: Throwable) {
        Log.w(tag, message, throwable)
    }

    override fun error(tag: String, message: String) {
        Log.e(tag, message)
    }

    override fun error(tag: String, message: String, throwable: Throwable) {
        Log.e(tag, message, throwable)
    }
}

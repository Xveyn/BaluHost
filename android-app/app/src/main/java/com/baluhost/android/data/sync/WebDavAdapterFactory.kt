package com.baluhost.android.data.sync

/**
 * Factory for creating `WebDavAdapter` instances with per-account credentials.
 */
interface WebDavAdapterFactory {
    fun create(username: String?, password: String?): WebDavAdapter
}

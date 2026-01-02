package com.baluhost.android.data.sync

import com.baluhost.android.domain.model.sync.FileEntry
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manager that creates per-account WebDAV adapters via the factory and provides convenience methods
 * for authentication and listing.
 */
@Singleton
class WebDavAccountManager @Inject constructor(private val factory: WebDavAdapterFactory) {

    fun createAdapter(username: String?, password: String?) = factory.create(username, password)

    suspend fun testCredentials(username: String?, password: String?): Boolean {
        val adapter = createAdapter(username, password)
        return try {
            adapter.authenticate()
        } catch (_: Exception) {
            false
        }
    }

    suspend fun listRemote(path: String, username: String?, password: String?): List<FileEntry> {
        val adapter = createAdapter(username, password)
        return adapter.list(path)
    }
}

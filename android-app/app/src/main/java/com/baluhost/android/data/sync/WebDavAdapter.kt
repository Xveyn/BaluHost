package com.baluhost.android.data.sync

import com.baluhost.android.domain.adapter.CloudAdapter
import com.baluhost.android.domain.model.sync.FileEntry
import com.baluhost.android.domain.model.sync.FolderStat
import com.baluhost.android.domain.model.sync.OperationResult
import okhttp3.Credentials
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import org.w3c.dom.NodeList
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import javax.xml.parsers.DocumentBuilderFactory

/**
 * WebDAV adapter using OkHttp for basic WebDAV operations (PROPFIND, GET, PUT, DELETE).
 * This implementation is intentionally lightweight and focuses on correctness for common servers.
 */
class WebDavAdapter(private val username: String? = null, private val password: String? = null) : CloudAdapter {

    private val client: OkHttpClient = OkHttpClient.Builder().build()

    private fun authHeader(): String? {
        if (username == null || password == null) return null
        return Credentials.basic(username, password)
    }

    override suspend fun authenticate(): Boolean {
        // No base URL provided here; caller should verify by calling stat/list on a known URL.
        return true
    }

    override suspend fun list(path: String): List<FileEntry> {
        try {
            val xml = propfind(path, depth = 1)
            return parsePropfindListing(xml, path)
        } catch (ex: Exception) {
            return emptyList()
        }
    }

    override suspend fun stat(path: String): FolderStat? {
        try {
            val xml = propfind(path, depth = 0)
            val docs = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(xml.byteInputStream())
            val hrefs = docs.getElementsByTagNameNS("*", "href")
            if (hrefs.length == 0) return null
            val href = hrefs.item(0).textContent
            val sizeNodes = docs.getElementsByTagNameNS("*", "getcontentlength")
            val size = if (sizeNodes.length > 0) sizeNodes.item(0).textContent.toLongOrNull() ?: 0L else 0L
            val modifiedNodes = docs.getElementsByTagNameNS("*", "getlastmodified")
            val modified = if (modifiedNodes.length > 0) parseDavDate(modifiedNodes.item(0).textContent) else System.currentTimeMillis()
            val nodeList = docs.getElementsByTagNameNS("*", "resourcetype")
            val isDir = nodeList.length > 0 && nodeList.item(0).textContent.contains("collection")
            return FolderStat(href, size, 0, modified)
        } catch (ex: Exception) {
            return null
        }
    }

    override suspend fun download(remotePath: String, localDstUri: String): OperationResult {
        try {
            val reqBuilder = Request.Builder().url(remotePath)
            authHeader()?.let { reqBuilder.header("Authorization", it) }
            val resp = client.newCall(reqBuilder.get().build()).execute()
            if (!resp.isSuccessful) return OperationResult(false, 0, 0, "http_${resp.code}")
            val body = resp.body ?: return OperationResult(false, 0, 0, "empty_body")
            val dst = File(java.net.URI(localDstUri))
            dst.parentFile?.mkdirs()
            val start = System.currentTimeMillis()
            body.byteStream().use { input -> dst.outputStream().use { output -> input.copyTo(output) } }
            val dur = System.currentTimeMillis() - start
            return OperationResult(true, dur, dst.length(), null)
        } catch (ex: Exception) {
            return OperationResult(false, 0, 0, ex.message)
        }
    }

    override suspend fun upload(localSrcUri: String, remotePath: String): OperationResult {
        try {
            val src = File(java.net.URI(localSrcUri))
            val media = "application/octet-stream".toMediaTypeOrNull()
            val body = RequestBody.create(media, src)
            val reqBuilder = Request.Builder().url(remotePath).put(body)
            authHeader()?.let { reqBuilder.header("Authorization", it) }
            val resp = client.newCall(reqBuilder.build()).execute()
            if (!resp.isSuccessful) return OperationResult(false, 0, 0, "http_${resp.code}")
            return OperationResult(true, 0, src.length(), null)
        } catch (ex: Exception) {
            return OperationResult(false, 0, 0, ex.message)
        }
    }

    override suspend fun delete(remotePath: String): OperationResult {
        try {
            val reqBuilder = Request.Builder().url(remotePath).delete()
            authHeader()?.let { reqBuilder.header("Authorization", it) }
            val resp = client.newCall(reqBuilder.build()).execute()
            if (!resp.isSuccessful) return OperationResult(false, 0, 0, "http_${resp.code}")
            return OperationResult(true, 0, 0, null)
        } catch (ex: Exception) {
            return OperationResult(false, 0, 0, ex.message)
        }
    }

    override fun supportsResume(): Boolean = false

    // --- Helpers ---
    private fun propfind(url: String, depth: Int = 0): String {
        val body = """<?xml version="1.0" encoding="utf-8"?>
            <d:propfind xmlns:d="DAV:">
              <d:allprop/>
            </d:propfind>
        """.trimIndent()

        val reqBuilder = Request.Builder().url(url).method("PROPFIND", RequestBody.create("text/xml".toMediaTypeOrNull(), body))
        reqBuilder.header("Depth", depth.toString())
        authHeader()?.let { reqBuilder.header("Authorization", it) }
        val resp = client.newCall(reqBuilder.build()).execute()
        if (!resp.isSuccessful) throw IllegalStateException("PROPFIND failed ${resp.code}")
        return resp.body?.string() ?: ""
    }

    private fun parsePropfindListing(xml: String, baseUrl: String): List<FileEntry> {
        val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(xml.byteInputStream())
        val responses = doc.getElementsByTagNameNS("*", "response")
        val out = mutableListOf<FileEntry>()
        for (i in 0 until responses.length) {
            val resp = responses.item(i)
            val hrefs = (resp as org.w3c.dom.Element).getElementsByTagNameNS("*", "href")
            if (hrefs.length == 0) continue
            val href = hrefs.item(0).textContent
            val propstats = resp.getElementsByTagNameNS("*", "propstat")
            var size = 0L
            var modified = System.currentTimeMillis()
            var isDir = false
            for (j in 0 until propstats.length) {
                val prop = (propstats.item(j) as org.w3c.dom.Element).getElementsByTagNameNS("*", "prop")
                if (prop.length == 0) continue
                val getcontentlength = (prop.item(0) as org.w3c.dom.Element).getElementsByTagNameNS("*", "getcontentlength")
                if (getcontentlength.length > 0) size = getcontentlength.item(0).textContent.toLongOrNull() ?: 0L
                val getlastmodified = (prop.item(0) as org.w3c.dom.Element).getElementsByTagNameNS("*", "getlastmodified")
                if (getlastmodified.length > 0) modified = parseDavDate(getlastmodified.item(0).textContent)
                val resType = (prop.item(0) as org.w3c.dom.Element).getElementsByTagNameNS("*", "resourcetype")
                if (resType.length > 0) isDir = resType.item(0).textContent.contains("collection")
            }
            val name = href.trimEnd('/').substringAfterLast('/')
            out.add(FileEntry(href, name, size, modified, isDir))
        }
        // Filter out the base path itself
        return out.filter { it.uri != baseUrl && it.name.isNotEmpty() }
    }

    private fun parseDavDate(value: String): Long {
        // Example: Tue, 15 Nov 1994 12:45:26 GMT
        return try {
            val fm = SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss zzz", Locale.US)
            fm.parse(value)?.time ?: System.currentTimeMillis()
        } catch (ex: Exception) {
            System.currentTimeMillis()
        }
    }
}

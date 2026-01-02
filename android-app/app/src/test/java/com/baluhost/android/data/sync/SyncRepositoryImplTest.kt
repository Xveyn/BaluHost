package com.baluhost.android.data.sync

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class SyncRepositoryImplTest {

    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun copyAndDelete_file_operations() = runBlocking {
        val helper = ExternalStorageHelper()
        val src = tmp.newFile("source.txt")
        src.writeText("hello world")

        val dstFile = File(tmp.root, "dst.txt")

        val (okCopy, dur) = helper.copyFileWithTiming(src.toURI().toString(), dstFile.toURI().toString())
        assertTrue(okCopy)
        assertTrue(dstFile.exists())
        assertEquals("hello world", dstFile.readText())
        assertTrue(dur >= 0)

        val (okDel, delDur) = helper.deleteWithTiming(dstFile.toURI().toString())
        assertTrue(okDel)
        assertFalse(dstFile.exists())
        assertTrue(delDur >= 0)
    }
}

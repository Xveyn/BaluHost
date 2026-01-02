package com.baluhost.android.domain.model

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

/**
 * Unit tests for CRDT (Conflict-free Replicated Data Type) implementation.
 */
class FileMetadataCRDTTest {
    
    @Test
    fun `merge with newer remote version should use remote`() {
        val local = createCRDT(version = 5L, deviceId = "device-a")
        val remote = createCRDT(version = 10L, deviceId = "device-b")
        
        val result = FileMetadataCRDT.merge(local, remote)
        
        assertEquals(10, result.version)
        assertEquals("device-b", result.deviceId)
    }
    
    @Test
    fun `merge with newer local version should use local`() {
        val local = createCRDT(version = 10L, deviceId = "device-a")
        val remote = createCRDT(version = 5L, deviceId = "device-b")
        
        val result = FileMetadataCRDT.merge(local, remote)
        
        assertEquals(10, result.version)
        assertEquals("device-a", result.deviceId)
    }
    
    @Test
    fun `merge with same version should use device ID tiebreaker`() {
        val local = createCRDT(version = 5L, deviceId = "device-a")
        val remote = createCRDT(version = 5L, deviceId = "device-b")
        
        val result = FileMetadataCRDT.merge(local, remote)
        
        // "device-b" > "device-a" alphabetically
        assertEquals(5, result.version)
        assertEquals("device-b", result.deviceId)
    }
    
    @Test
    fun `shouldApplyUpdate returns true for newer remote`() {
        val local = createCRDT(version = 5L, deviceId = "device-a")
        val remote = createCRDT(version = 10L, deviceId = "device-b")
        
        val result = FileMetadataCRDT.shouldApplyUpdate(local, remote)
        
        assertTrue(result)
    }
    
    @Test
    fun `shouldApplyUpdate returns false for older remote`() {
        val local = createCRDT(version = 10L, deviceId = "device-a")
        val remote = createCRDT(version = 5L, deviceId = "device-b")
        
        val result = FileMetadataCRDT.shouldApplyUpdate(local, remote)
        
        assertFalse(result)
    }
    
    @Test
    fun `incrementVersion should bump version and update deviceId`() {
        val original = createCRDT(version = 5L, deviceId = "device-a")
        
        val updated = original.incrementVersion("device-b")
        
        assertEquals(6, updated.version)
        assertEquals("device-b", updated.deviceId)
        // Accept non-decreasing modifiedAt to avoid flakiness on fast test runs
        assertFalse(updated.modifiedAt.isBefore(original.modifiedAt))
    }
    
    @Test
    fun `isNewerThan should return true for higher version`() {
        val older = createCRDT(version = 5L, deviceId = "device-a")
        val newer = createCRDT(version = 10L, deviceId = "device-a")
        
        assertTrue(newer.isNewerThan(older))
        assertFalse(older.isNewerThan(newer))
    }
    
    @Test
    fun `vector clock increment should increase device version`() {
        val clock = VectorClock(mapOf("device-a" to 5L))
        
        val incremented = clock.increment("device-a")
        
        assertEquals(6L, incremented.clocks["device-a"])
    }
    
    @Test
    fun `vector clock increment for new device should start at 1`() {
        val clock = VectorClock(emptyMap())
        
        val incremented = clock.increment("device-new")
        
        assertEquals(1L, incremented.clocks["device-new"])
    }
    
    @Test
    fun `vector clock merge should take max of each device`() {
        val clock1 = VectorClock(mapOf("device-a" to 10L, "device-b" to 5L))
        val clock2 = VectorClock(mapOf("device-a" to 7L, "device-b" to 8L, "device-c" to 3L))
        
        val merged = clock1.merge(clock2)
        
        assertEquals(10L, merged.clocks["device-a"])  // max(10, 7)
        assertEquals(8L, merged.clocks["device-b"])   // max(5, 8)
        assertEquals(3L, merged.clocks["device-c"])   // max(0, 3)
    }
    
    @Test
    fun `vector clock happensBefore should detect causal relationship`() {
        val earlier = VectorClock(mapOf("device-a" to 5, "device-b" to 2))
        val later = VectorClock(mapOf("device-a" to 10, "device-b" to 5))
        
        assertTrue(earlier.happensBefore(later))
        assertFalse(later.happensBefore(earlier))
    }
    
    @Test
    fun `vector clock isConcurrentWith should detect concurrent updates`() {
        val clock1 = VectorClock(mapOf("device-a" to 10, "device-b" to 2))
        val clock2 = VectorClock(mapOf("device-a" to 5, "device-b" to 8))
        
        assertTrue(clock1.isConcurrentWith(clock2))
        assertTrue(clock2.isConcurrentWith(clock1))
    }
    
    @Test(expected = IllegalArgumentException::class)
    fun `merge with different file paths should throw exception`() {
        val file1 = createCRDT(path = "/path/to/file1.txt")
        val file2 = createCRDT(path = "/path/to/file2.txt")
        
        FileMetadataCRDT.merge(file1, file2)
    }
    
    // Helper function to create test CRDTs
    private fun createCRDT(
        path: String = "/test/file.txt",
        version: Long = 1,
        deviceId: String = "device-test"
    ): FileMetadataCRDT {
        return FileMetadataCRDT(
            path = path,
            name = "file.txt",
            size = 1024,
            isDirectory = false,
            modifiedAt = Instant.now(),
            version = version,
            deviceId = deviceId
        )
    }
}

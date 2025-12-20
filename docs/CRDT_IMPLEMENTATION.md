# CRDT (Conflict-free Replicated Data Types) Implementation

## Overview

BaluHost Android App uses **CRDTs** to handle concurrent file updates from multiple devices without conflicts. This ensures that offline changes can be merged deterministically when devices come back online.

## What are CRDTs?

**Conflict-free Replicated Data Types** are data structures that can be replicated across multiple devices and updated independently. When replicas sync, updates are merged automatically using mathematical properties that guarantee:

1. **Convergence**: All replicas eventually reach the same state
2. **No Conflicts**: Merging is deterministic (same result regardless of merge order)
3. **No Coordination**: Devices can update independently without talking to each other

## Implementation Strategy

We use **Last-Write-Wins (LWW)** CRDT with **Lamport timestamps**:

### Key Components

#### 1. FileMetadataCRDT
```kotlin
data class FileMetadataCRDT(
    val path: String,
    val name: String,
    val size: Long,
    val isDirectory: Boolean,
    val modifiedAt: Instant,
    val version: Long,        // Lamport timestamp
    val deviceId: String,     // Device that made last change
    val checksum: String?     // For detecting file changes
)
```

#### 2. Merge Rules
```kotlin
fun merge(local: FileMetadataCRDT, remote: FileMetadataCRDT): FileMetadataCRDT {
    return when {
        remote.version > local.version -> remote  // Remote is newer
        local.version > remote.version -> local   // Local is newer
        remote.deviceId > local.deviceId -> remote  // Tiebreaker
        else -> local
    }
}
```

#### 3. Vector Clocks (Advanced)
For tracking causal dependencies between updates:

```kotlin
data class VectorClock(
    val clocks: Map<String, Long>  // deviceId -> version
)
```

## How It Works

### Scenario 1: Simple Update
```
Device A (offline):
- Edits file.txt → version = 5, device = "A"

Server (online):
- Has version = 3, device = "C"

Merge Result:
- version = 5, device = "A" (newer wins)
```

### Scenario 2: Concurrent Updates
```
Device A (offline):
- Edits file.txt → version = 5, device = "A"

Device B (offline):
- Edits file.txt → version = 5, device = "B"

Both come online:
Merge Result:
- version = 5, device = "B" (tiebreaker: "B" > "A")
```

### Scenario 3: Vector Clock Tracking
```
Device A timeline:
v1: {A: 1, B: 0, C: 0}  // A makes change
v2: {A: 2, B: 1, C: 0}  // A sees B's change
v3: {A: 3, B: 1, C: 0}  // A makes another change

Device B timeline:
v1: {A: 0, B: 1, C: 0}  // B makes change
v2: {A: 1, B: 2, C: 0}  // B sees A's change

Merge:
{A: 3, B: 2, C: 0}  // Max of each device
```

## Integration with Offline Queue

The `OfflineQueueManager` uses CRDT logic for conflict resolution:

### Automatic Retry with CRDT Merge
```kotlin
// When server comes online
retryPendingOperations() {
    operations.forEach { op ->
        // Check if our version is newer
        if (shouldApplyLocalChange(
            localVersion = op.version,
            localDeviceId = deviceId,
            remoteVersion = serverVersion,
            remoteDeviceId = serverDeviceId
        )) {
            // Apply our change
            uploadUpdate(op)
        } else {
            // Server has newer version, discard ours
            markAsObsolete(op)
        }
    }
}
```

### Exponential Backoff
```kotlin
Retry Schedule:
- Attempt 1: 0ms delay
- Attempt 2: 1s delay
- Attempt 3: 2s delay
- Attempt 4: 4s delay
- Attempt 5: 8s delay
- Max: 60s delay
```

## Benefits

### ✅ Offline-First
- Users can edit files offline on multiple devices
- Changes are queued and synced automatically
- No data loss

### ✅ Deterministic Merging
- Same merge result regardless of sync order
- No "unexpected conflicts" for users
- Automatic resolution

### ✅ Scalable
- Works with any number of devices
- No central coordinator needed
- Eventually consistent

## Limitations

### ⚠️ Last-Write-Wins Trade-off
- Only the latest change survives (others are discarded)
- Not suitable for collaborative editing of text files
- Use case: File metadata, folder structure

### 🔧 When to Use
✅ File metadata (name, size, permissions)
✅ Folder structure
✅ User preferences
❌ Collaborative text editing (use OT/CRDT-Text instead)
❌ Spreadsheets with formulas

## Future Enhancements

### 1. CRDT-Text for Collaborative Editing
- Use **Yjs** or **Automerge** for text documents
- Character-by-character merge
- Preserves all edits

### 2. Custom Merge Strategies
```kotlin
interface MergeStrategy {
    fun merge(local: T, remote: T): T
}

class AddWinsMerge : MergeStrategy<Set<String>> {
    // Both additions survive, deletions are ignored
}

class DeleteWinsMerge : MergeStrategy<Set<String>> {
    // Deletions override additions
}
```

### 3. Conflict Notification
```kotlin
if (local.isConcurrentWith(remote)) {
    // Notify user about concurrent changes
    showConflictDialog(local, remote, merged)
}
```

## Testing

Run CRDT unit tests:
```bash
./gradlew test --tests FileMetadataCRDTTest
```

### Test Coverage
- ✅ LWW merge (newer version wins)
- ✅ Tiebreaker (device ID comparison)
- ✅ Version increment
- ✅ Vector clock operations
- ✅ Causal dependency detection
- ✅ Concurrent update detection

## References

- [CRDT Paper (Shapiro et al.)](https://hal.inria.fr/inria-00555588/document)
- [Lamport Timestamps](https://en.wikipedia.org/wiki/Lamport_timestamp)
- [Vector Clocks](https://en.wikipedia.org/wiki/Vector_clock)
- [Automerge CRDT Library](https://automerge.org/)

## API Example

```kotlin
// In ViewModel
val localFile = FileMetadataCRDT(
    path = "/docs/report.pdf",
    version = 5,
    deviceId = preferencesManager.getDeviceId()
)

val remoteFile = FileMetadataCRDT(
    path = "/docs/report.pdf",
    version = 3,
    deviceId = "server"
)

// Merge
val merged = FileMetadataCRDT.merge(localFile, remoteFile)
// Result: version=5, deviceId=local (local is newer)

// Update
val updated = merged.incrementVersion(myDeviceId)
// Result: version=6, deviceId=myDeviceId
```

## Summary

CRDTs enable **offline-first**, **conflict-free** file synchronization across multiple devices. The BaluHost implementation uses a simple **Last-Write-Wins** strategy with **Lamport timestamps** and optional **Vector Clocks** for causal tracking.

**Key Principle**: Mathematical properties guarantee convergence → No manual conflict resolution needed! 🎉

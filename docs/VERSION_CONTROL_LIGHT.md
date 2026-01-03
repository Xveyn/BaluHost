# Version Control Light (VCL) - Implementation Roadmap

## 📋 Executive Summary

Version Control Light ist ein intelligentes Versionskontrollsystem für kleine Dateien (<100 MB), das automatisch Änderungen speichert und Wiederherstellung ermöglicht. Das System nutzt Checksum-basierte Änderungserkennung, intelligentes Caching und Kompression für optimale Speichernutzung.

### Key Features
- ✅ Automatische Versionierung mit Checksum-Deduplizierung
- ✅ Pro-User Speicherlimits (Admin-gesteuert)
- ✅ Intelligentes Caching bei schnellen Änderungen
- ✅ Kompression aller Versionen (gzip)
- ✅ Priority-Mode für Speicherverwaltung
- ✅ Version Diff Viewer
- ✅ ZIP-Export für Admins
- ✅ High-Priority Flag für wichtige Dateien

---

## 🎯 Core Funktionalität

### 1. Automatische Versionierung

#### Trigger-Bedingungen
```python
def should_create_version(file: File, new_checksum: str) -> bool:
    """
    Versionierung nur wenn:
    1. Datei <= 100 MB
    2. Checksum unterscheidet sich von letzter Version
    3. User hat nicht Quota überschritten
    4. Nicht in Caching-Window (siehe Intelligent Caching)
    """
    if file.size > 100 * 1024 * 1024:
        return False
    
    last_version = get_last_version(file.id)
    if last_version and last_version.checksum == new_checksum:
        return False  # Keine Änderung
    
    user_quota = get_user_vcl_quota(file.user_id)
    if user_quota.is_exceeded():
        return False
    
    if is_in_caching_window(file.id):
        return False  # Warte auf Cache-Flush
    
    return True
```

#### Checksum-basierte Änderungserkennung
- **Algorithmus:** SHA256 für Dateiinhalt
- **Deduplizierung:** Gleiche Checksums → Hardlink/Referenz statt neue Kopie
- **Storage-Optimierung:** Speichere nur einzigartige Blobs

```python
# Beispiel: Deduplizierung
existing_blob = find_blob_by_checksum(checksum)
if existing_blob:
    # Keine neue Datei speichern, nur Metadaten
    version.blob_id = existing_blob.id
    version.storage_type = 'reference'
else:
    # Neue komprimierte Datei speichern
    compressed_path = compress_and_store(file_content)
    version.blob_id = create_blob(compressed_path, checksum)
    version.storage_type = 'stored'
```

### 2. Intelligentes Caching

#### Problem
Schnelle aufeinanderfolgende Änderungen (z.B. bei Save-on-Type oder Auto-Save) würden zu vielen unnötigen Versionen führen.

#### Lösung: Debouncing + Batching

```python
class VCLCache:
    """
    Caching-Strategie:
    - Sammle Änderungen für X Sekunden
    - Speichere nur finale Version nach Inaktivität
    - Bei Force-Flush (z.B. User-Logout) sofort speichern
    """
    
    DEBOUNCE_WINDOW = 30  # Sekunden
    MAX_BATCH_WINDOW = 300  # 5 Minuten (Hard-Limit)
    
    pending_changes: Dict[int, PendingVersion] = {}
    
    @classmethod
    async def queue_version(cls, file_id: int, content: bytes, checksum: str):
        """Queue eine potentielle Version"""
        now = time.time()
        
        if file_id in cls.pending_changes:
            pending = cls.pending_changes[file_id]
            # Update pending change
            pending.content = content
            pending.checksum = checksum
            pending.last_modified = now
            
            # Hard-Limit erreicht?
            if now - pending.first_modified > cls.MAX_BATCH_WINDOW:
                await cls.flush_version(file_id)
        else:
            # Neue pending change
            cls.pending_changes[file_id] = PendingVersion(
                content=content,
                checksum=checksum,
                first_modified=now,
                last_modified=now
            )
            
            # Schedule Debounce-Flush
            asyncio.create_task(cls.debounced_flush(file_id))
    
    @classmethod
    async def debounced_flush(cls, file_id: int):
        """Warte auf Inaktivität, dann flush"""
        await asyncio.sleep(cls.DEBOUNCE_WINDOW)
        
        if file_id not in cls.pending_changes:
            return  # Bereits geflusht
        
        pending = cls.pending_changes[file_id]
        if time.time() - pending.last_modified >= cls.DEBOUNCE_WINDOW:
            await cls.flush_version(file_id)
        else:
            # Weitere Änderungen kamen rein, reschedule
            await cls.debounced_flush(file_id)
    
    @classmethod
    async def flush_version(cls, file_id: int):
        """Erstelle tatsächliche Version"""
        if file_id not in cls.pending_changes:
            return
        
        pending = cls.pending_changes.pop(file_id)
        await create_version(
            file_id=file_id,
            content=pending.content,
            checksum=pending.checksum,
            change_type='batched'
        )
```

#### Best Practices
- **Debounce Window:** 30 Sekunden (konfigurierbar)
- **Max Batch Window:** 5 Minuten (verhindert Datenverlust)
- **Force Flush Events:**
  - User Logout
  - System Shutdown
  - Manual Save
  - File Close (im FileExplorer)

### 3. Kompression

#### Strategie
Alle Versionen werden mit gzip komprimiert gespeichert, um Speicherplatz zu sparen.

```python
import gzip
import shutil

def compress_version_file(source_path: Path, dest_path: Path) -> int:
    """
    Komprimiere Datei mit gzip (Level 6 = Balance)
    Returns: Komprimierte Größe in Bytes
    """
    with open(source_path, 'rb') as f_in:
        with gzip.open(dest_path, 'wb', compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
    
    return dest_path.stat().st_size

def decompress_version_file(compressed_path: Path, dest_path: Path):
    """Dekomprimiere für Restore oder Download"""
    with gzip.open(compressed_path, 'rb') as f_in:
        with open(dest_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
```

#### Kompressionsraten (Durchschnitt)
- Text-Dateien: 70-90% Reduktion
- Code-Dateien: 60-80% Reduktion
- JSON/XML: 80-95% Reduktion
- Binär-Dateien: 10-30% Reduktion (bereits komprimiert)
- Office-Dokumente: 5-15% Reduktion (bereits komprimiert)

#### Storage-Layout
```
storage/
  versions/
    blobs/                      # Deduplizierte Blobs
      <checksum>.gz             # Komprimierte Dateiinhalte
    metadata/
      <file_id>/
        v001.json               # Metadaten pro Version
        v002.json
```

---

## 🗄️ Datenbankschema

### Tabelle: `file_versions`

```sql
CREATE TABLE file_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,                    
    user_id INTEGER NOT NULL,                    
    version_number INTEGER NOT NULL,             
    
    -- Storage Information
    blob_id INTEGER,                             -- Referenz zu version_blobs
    storage_type TEXT NOT NULL,                  -- 'stored', 'reference' (dedupliziert)
    file_size INTEGER NOT NULL,                  -- Originalgröße (unkomprimiert)
    compressed_size INTEGER NOT NULL,            -- Komprimierte Größe
    compression_ratio REAL,                      -- file_size / compressed_size
    
    -- Checksums & Integrity
    checksum TEXT NOT NULL,                      -- SHA256
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_high_priority BOOLEAN DEFAULT FALSE,      
    change_type TEXT,                            -- 'create', 'update', 'overwrite', 'batched'
    comment TEXT,                                
    
    -- Caching Info
    was_cached BOOLEAN DEFAULT FALSE,            -- Aus Cache geflusht?
    cache_duration INTEGER,                      -- Sekunden im Cache
    
    FOREIGN KEY (file_id) REFERENCES file_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (blob_id) REFERENCES version_blobs(id) ON DELETE SET NULL,
    UNIQUE(file_id, version_number)
);

CREATE INDEX idx_file_versions_file_id ON file_versions(file_id);
CREATE INDEX idx_file_versions_user_id ON file_versions(user_id);
CREATE INDEX idx_file_versions_checksum ON file_versions(checksum);
CREATE INDEX idx_file_versions_priority ON file_versions(is_high_priority);
```

### Tabelle: `version_blobs` (Deduplizierung)

```sql
CREATE TABLE version_blobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checksum TEXT UNIQUE NOT NULL,               -- SHA256 als Key
    storage_path TEXT NOT NULL,                  -- Pfad zur .gz Datei
    original_size INTEGER NOT NULL,
    compressed_size INTEGER NOT NULL,
    reference_count INTEGER DEFAULT 0,           -- Wie viele Versionen nutzen diesen Blob
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP,
    
    -- Cleanup-Info
    can_delete BOOLEAN DEFAULT FALSE             -- Wird auf TRUE wenn reference_count = 0
);

CREATE INDEX idx_version_blobs_checksum ON version_blobs(checksum);
CREATE INDEX idx_version_blobs_cleanup ON version_blobs(can_delete, last_accessed);
```

### Tabelle: `vcl_settings` (Pro-User Limits)

```sql
CREATE TABLE vcl_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,                      -- NULL = globale Settings
    
    -- Speicherlimits
    max_size_bytes INTEGER NOT NULL DEFAULT 10737418240,  -- 10 GB
    current_usage_bytes INTEGER DEFAULT 0,       -- Aktuell genutzt
    
    -- Versioning-Parameter
    depth INTEGER NOT NULL DEFAULT 5,            -- Max Versionen pro Datei
    headroom_percent INTEGER NOT NULL DEFAULT 10,
    
    -- Feature-Flags
    is_enabled BOOLEAN DEFAULT TRUE,
    compression_enabled BOOLEAN DEFAULT TRUE,
    dedupe_enabled BOOLEAN DEFAULT TRUE,
    
    -- Caching-Parameter
    debounce_window_seconds INTEGER DEFAULT 30,
    max_batch_window_seconds INTEGER DEFAULT 300,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_vcl_settings_user ON vcl_settings(user_id);
```

### Tabelle: `vcl_stats`

```sql
CREATE TABLE vcl_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Global Stats
    total_versions INTEGER DEFAULT 0,
    total_size_bytes INTEGER DEFAULT 0,           -- Unkomprimiert
    total_compressed_bytes INTEGER DEFAULT 0,     -- Komprimiert
    total_blobs INTEGER DEFAULT 0,
    unique_blobs INTEGER DEFAULT 0,               -- Dedupliziert
    
    -- Savings
    deduplication_savings_bytes INTEGER DEFAULT 0,
    compression_savings_bytes INTEGER DEFAULT 0,
    
    -- Priority & Features
    priority_count INTEGER DEFAULT 0,
    cached_versions_count INTEGER DEFAULT 0,
    
    -- Maintenance
    last_cleanup_at TIMESTAMP,
    last_priority_mode_at TIMESTAMP,
    last_deduplication_scan TIMESTAMP,
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🔌 API Specification

### Admin Endpoints

#### 1. User VCL Settings Management
```http
GET /api/admin/vcl/settings
Response: List[UserVCLSettings]

GET /api/admin/vcl/settings/{user_id}
Response: UserVCLSettings

PUT /api/admin/vcl/settings/{user_id}
Request: {
  "max_size_bytes": 21474836480,  // 20 GB
  "depth": 10,
  "headroom_percent": 15,
  "is_enabled": true,
  "compression_enabled": true,
  "dedupe_enabled": true
}
Response: UserVCLSettings
```

#### 2. VCL Statistics & Monitoring
```http
GET /api/admin/vcl/stats
Response: {
  "global": VCLStats,
  "per_user": List[UserVCLStats],
  "storage_breakdown": {
    "total_versions": 1234,
    "total_size_mb": 50000,
    "compressed_size_mb": 15000,
    "compression_ratio": 3.33,
    "deduplication_savings_mb": 5000
  }
}

GET /api/admin/vcl/versions
Query: ?user_id=X&limit=100&offset=0&sort_by=created_at&order=desc
Response: {
  "versions": List[FileVersion],
  "total": 1234,
  "page": 1,
  "pages": 13
}
```

#### 3. VCL Container Export (ZIP Download)
```http
POST /api/admin/vcl/export
Request: {
  "user_id": 5,                    // Optional: Nur dieser User
  "file_ids": [10, 20, 30],        // Optional: Nur diese Dateien
  "include_metadata": true,         // JSON-Metadaten inkludieren?
  "decompress": false               // Als .gz oder entpackt?
}
Response: {
  "export_id": "exp_abc123",
  "status": "preparing",            // preparing, ready, failed
  "download_url": null,             // Wird gesetzt wenn ready
  "expires_at": "2026-01-03T10:00:00Z"
}

GET /api/admin/vcl/export/{export_id}
Response: {
  "export_id": "exp_abc123",
  "status": "ready",
  "download_url": "/api/admin/vcl/export/exp_abc123/download",
  "file_count": 156,
  "total_size_bytes": 1234567890,
  "created_at": "2026-01-02T23:05:00Z",
  "expires_at": "2026-01-03T10:00:00Z"
}

GET /api/admin/vcl/export/{export_id}/download
Response: application/zip (Stream)
Headers:
  Content-Disposition: attachment; filename="vcl_export_{timestamp}.zip"
  Content-Length: 1234567890
```

**ZIP Structure:**
```
vcl_export_20260102_230500/
  metadata.json                    # Export-Info
  user_5/
    file_10_document.txt/
      v001/
        content.txt (.gz wenn decompress=false)
        metadata.json
      v002/
        content.txt
        metadata.json
    file_20_report.pdf/
      v001/
        content.pdf
        metadata.json
  manifest.json                    # Dateiliste, Checksums
```

#### 4. Manual Cleanup & Maintenance
```http
POST /api/admin/vcl/cleanup
Request: {
  "force_priority_mode": true,     // Lösche alte Versionen
  "target_user_id": null,           // Null = alle
  "dry_run": false                  // Nur simulieren?
}
Response: {
  "deleted_versions": 45,
  "freed_bytes": 1234567890,
  "deleted_blobs": 12,
  "duration_seconds": 2.5
}

POST /api/admin/vcl/deduplication-scan
Response: {
  "scanned_blobs": 1234,
  "found_duplicates": 56,
  "saved_bytes": 234567890
}
```

### User Endpoints

#### 1. File Versions
```http
GET /api/files/{file_id}/versions
Response: {
  "file_id": 10,
  "file_name": "document.txt",
  "versions": [
    {
      "id": 101,
      "version_number": 3,
      "file_size": 1024,
      "compressed_size": 256,
      "checksum": "abc123...",
      "created_at": "2026-01-02T10:00:00Z",
      "is_high_priority": false,
      "change_type": "update",
      "can_restore": true,
      "can_delete": true,
      "storage_type": "stored"
    }
  ],
  "current_version": 3,
  "total_versions": 3,
  "total_size_bytes": 3072,
  "user_quota": {
    "used_bytes": 50000000,
    "max_bytes": 10737418240,
    "percent_used": 0.47
  }
}

GET /api/files/{file_id}/versions/{version_id}
Response: FileVersion (detailed)

GET /api/files/{file_id}/versions/{version_id}/download
Response: File Stream (dekomprimiert)

POST /api/files/{file_id}/versions/{version_id}/restore
Response: {
  "success": true,
  "message": "File restored to version 2",
  "new_current_version": 4  // Restore erstellt neue Version
}
```

#### 2. Version Diff Viewer
```http
GET /api/files/{file_id}/versions/{version_id}/diff
Query: ?compare_to={other_version_id}
Response: {
  "version_a": 2,
  "version_b": 3,
  "file_type": "text/plain",
  "diff_available": true,
  "diff_format": "unified",    // unified, side-by-side, json
  "diff": "--- Version 2\n+++ Version 3\n@@ -1,3 +1,3 @@\n Hello\n-World\n+Universe\n"
}

# Für nicht-text Dateien:
Response: {
  "version_a": 2,
  "version_b": 3,
  "file_type": "application/pdf",
  "diff_available": false,
  "comparison": {
    "size_change_bytes": 1024,
    "checksum_a": "abc...",
    "checksum_b": "def...",
    "identical": false
  }
}
```

#### 3. Priority Flag Management
```http
PUT /api/files/{file_id}/priority
Request: {
  "is_high_priority": true,
  "apply_to_versions": "all"  // all, future, none
}
Response: {
  "file_id": 10,
  "is_high_priority": true,
  "affected_versions": 3
}
```

#### 4. Version Deletion (Own Only)
```http
DELETE /api/files/{file_id}/versions/{version_id}
Response: {
  "success": true,
  "message": "Version 2 deleted",
  "remaining_versions": 2,
  "freed_bytes": 256
}
```

---

## 🎨 Frontend Implementation

### 1. Settings Page - VCL Tab (Admin)

#### Component Structure
```tsx
// client/src/pages/settings/VCLSettings.tsx

interface VCLSettingsProps {
  isAdmin: boolean;
}

const VCLSettings: React.FC<VCLSettingsProps> = ({ isAdmin }) => {
  // State
  const [globalSettings, setGlobalSettings] = useState<VCLSettings | null>(null);
  const [userSettings, setUserSettings] = useState<UserVCLSettings[]>([]);
  const [stats, setStats] = useState<VCLStats | null>(null);
  
  // UI Sections:
  // 1. Global Settings Card (wenn Admin)
  // 2. Per-User Settings Table
  // 3. Statistics Dashboard
  // 4. Maintenance Actions
  
  return (
    <div className="vcl-settings-container">
      {/* Global Settings */}
      <VCLGlobalSettings settings={globalSettings} onChange={...} />
      
      {/* Per-User Limits */}
      <VCLUserLimitsTable users={userSettings} onEdit={...} />
      
      {/* Stats Dashboard */}
      <VCLStatsDashboard stats={stats} />
      
      {/* Maintenance */}
      <VCLMaintenancePanel onCleanup={...} onExport={...} />
    </div>
  );
};
```

#### UI Elements

**Global Settings Card:**
```tsx
- Enable/Disable Toggle (Global Master Switch)
- Default Max Size Slider (0 - 100 GB)
- Default Depth Input (1 - 50)
- Default Headroom Slider (0 - 50%)
- Compression Toggle
- Deduplication Toggle
- Caching Settings:
  - Debounce Window (10-120 seconds)
  - Max Batch Window (1-30 minutes)
```

**Per-User Limits Table:**
```tsx
| User | Max Size | Used | % | Depth | Priority Files | Actions |
|------|----------|------|---|-------|----------------|---------|
| admin | 50 GB | 5 GB | 10% | 10 | 3 | Edit, Export |
| john  | 20 GB | 18 GB| 90% | 5 | 12 | Edit, Export |
```

**Stats Dashboard:**
```tsx
- Total Versions: 1,234
- Total Storage (Original): 50 GB
- Total Storage (Compressed): 15 GB
- Compression Ratio: 3.33x
- Deduplication Savings: 5 GB
- Unique Blobs: 456
- Last Cleanup: 2 hours ago
- Storage Usage Chart (per User)
```

**Maintenance Panel:**
```tsx
<div className="maintenance-actions">
  <button onClick={runCleanup}>
    <Trash2 /> Run Cleanup
  </button>
  
  <button onClick={runDeduplication}>
    <Database /> Deduplicate Blobs
  </button>
  
  <button onClick={exportAllVersions}>
    <Download /> Export All Versions (ZIP)
  </button>
  
  <button onClick={exportUserVersions}>
    <Download /> Export User Versions
  </button>
</div>
```

### 2. File Explorer Integration

#### Version Icon & Indicator
```tsx
// In FileManager Grid/List Item
<div className="file-item">
  <FileIcon type={file.type} />
  <span className="file-name">{file.name}</span>
  
  {file.has_versions && (
    <Tooltip content={`${file.version_count} versions available`}>
      <Clock className="version-indicator text-blue-400" size={16} />
    </Tooltip>
  )}
  
  {file.is_high_priority && (
    <Tooltip content="High priority for VCL">
      <Star className="priority-indicator text-yellow-400" size={16} fill="currentColor" />
    </Tooltip>
  )}
</div>
```

#### Context Menu Extension
```tsx
// Rechtsklick-Menü erweitern
const contextMenuItems = [
  // ... existing items
  { separator: true },
  {
    label: 'Version History',
    icon: <History />,
    onClick: () => openVersionHistoryModal(file),
    disabled: !file.has_versions
  },
  {
    label: file.is_high_priority ? 'Remove Priority' : 'Mark as High Priority',
    icon: <Star />,
    onClick: () => togglePriority(file)
  }
];
```

### 3. Version History Modal

```tsx
// client/src/components/modals/VersionHistoryModal.tsx

interface VersionHistoryModalProps {
  fileId: number;
  fileName: string;
  onClose: () => void;
}

const VersionHistoryModal: React.FC<VersionHistoryModalProps> = ({
  fileId,
  fileName,
  onClose
}) => {
  const [versions, setVersions] = useState<FileVersion[]>([]);
  const [selectedVersions, setSelectedVersions] = useState<[number, number] | null>(null);
  const [diffView, setDiffView] = useState<DiffResult | null>(null);
  
  return (
    <Modal size="xl" onClose={onClose}>
      <Modal.Header>
        <History /> Version History: {fileName}
      </Modal.Header>
      
      <Modal.Body>
        {/* Version List */}
        <div className="version-list">
          {versions.map(version => (
            <VersionListItem
              key={version.id}
              version={version}
              isCurrent={version.version_number === versions.length}
              onRestore={() => restoreVersion(version.id)}
              onDownload={() => downloadVersion(version.id)}
              onDelete={() => deleteVersion(version.id)}
              onCompare={() => selectForCompare(version)}
              isSelected={selectedVersions?.includes(version.id)}
            />
          ))}
        </div>
        
        {/* Diff Viewer (wenn 2 Versionen gewählt) */}
        {diffView && (
          <DiffViewer
            versionA={diffView.version_a}
            versionB={diffView.version_b}
            diff={diffView.diff}
            format={diffView.diff_format}
          />
        )}
        
        {/* Quota Info */}
        <QuotaBar
          used={quotaInfo.used_bytes}
          max={quotaInfo.max_bytes}
        />
      </Modal.Body>
      
      <Modal.Footer>
        <button onClick={onClose}>Close</button>
      </Modal.Footer>
    </Modal>
  );
};
```

#### Version List Item Design
```tsx
<div className="version-item">
  <div className="version-header">
    <span className="version-number">v{version.version_number}</span>
    {version.is_high_priority && <Star className="priority-badge" />}
    <span className="version-date">{formatDate(version.created_at)}</span>
  </div>
  
  <div className="version-details">
    <span className="file-size">{formatBytes(version.file_size)}</span>
    <span className="compressed">
      ({formatBytes(version.compressed_size)} compressed)
    </span>
    <span className="change-type badge">{version.change_type}</span>
  </div>
  
  <div className="version-actions">
    <button onClick={onDownload}><Download size={16} /></button>
    <button onClick={onRestore}><RotateCcw size={16} /></button>
    <button onClick={onCompare}><GitCompare size={16} /></button>
    <button onClick={onDelete}><Trash2 size={16} /></button>
  </div>
</div>
```

### 4. Diff Viewer Component

```tsx
// client/src/components/vcl/DiffViewer.tsx

interface DiffViewerProps {
  versionA: number;
  versionB: number;
  diff: string;
  format: 'unified' | 'side-by-side' | 'json';
}

const DiffViewer: React.FC<DiffViewerProps> = ({ diff, format }) => {
  if (format === 'unified') {
    return (
      <div className="diff-viewer unified">
        <pre className="diff-content">
          {diff.split('\n').map((line, i) => (
            <div
              key={i}
              className={
                line.startsWith('+') ? 'diff-addition' :
                line.startsWith('-') ? 'diff-deletion' :
                line.startsWith('@@') ? 'diff-hunk' :
                'diff-context'
              }
            >
              {line}
            </div>
          ))}
        </pre>
      </div>
    );
  }
  
  // Side-by-side view
  return (
    <div className="diff-viewer side-by-side">
      <div className="diff-pane left">{/* Version A */}</div>
      <div className="diff-pane right">{/* Version B */}</div>
    </div>
  );
};
```

### 5. Database Page Integration

#### VCL Tables in Database View
```tsx
// In AdminDatabase.tsx
const VCL_TABLES = ['file_versions', 'version_blobs', 'vcl_settings', 'vcl_stats'];

// Spezielle Formatierung für VCL-Tabellen
const formatVCLTableData = (tableName: string, row: any) => {
  if (tableName === 'file_versions') {
    return {
      ...row,
      file_size: formatBytes(row.file_size),
      compressed_size: formatBytes(row.compressed_size),
      compression_ratio: `${row.compression_ratio?.toFixed(2)}x`,
      storage_type: <Badge>{row.storage_type}</Badge>
    };
  }
  // ... weitere Tabellen
};
```

#### VCL Dashboard Widget
```tsx
// Neues Widget im Database-Overview
<div className="vcl-dashboard-widget">
  <h3>VCL Storage Overview</h3>
  
  <div className="vcl-stats-grid">
    <StatCard
      label="Total Versions"
      value={stats.total_versions}
      icon={<Clock />}
    />
    <StatCard
      label="Storage Used"
      value={formatBytes(stats.total_compressed_bytes)}
      sublabel={`${formatBytes(stats.total_size_bytes)} original`}
      icon={<HardDrive />}
    />
    <StatCard
      label="Compression Savings"
      value={`${((1 - stats.total_compressed_bytes / stats.total_size_bytes) * 100).toFixed(1)}%`}
      icon={<Archive />}
    />
    <StatCard
      label="Dedup Savings"
      value={formatBytes(stats.deduplication_savings_bytes)}
      icon={<Copy />}
    />
  </div>
  
  <VCLStorageChart data={statsPerUser} />
</div>
```

---

## 🚀 Implementation Roadmap

### Phase 1: Core Backend (Weeks 1-2)

#### Week 1: Foundation
**Day 1-2: Database Schema**
- [ ] Create migration: `file_versions` table
- [ ] Create migration: `version_blobs` table
- [ ] Create migration: `vcl_settings` table
- [ ] Create migration: `vcl_stats` table
- [ ] Add indexes and foreign keys
- [ ] Test migrations up/down

**Day 3-4: Core Services**
- [ ] Implement `VCLService` class
- [ ] Checksum generation (SHA256)
- [ ] Compression utilities (gzip)
- [ ] Blob storage management
- [ ] Deduplication logic

**Day 5: Settings & Quota**
- [ ] User quota calculation
- [ ] Settings management (global + per-user)
- [ ] Quota enforcement in upload hook

#### Week 2: Advanced Features
**Day 6-7: Intelligent Caching**
- [ ] Implement `VCLCache` class
- [ ] Debouncing mechanism
- [ ] Batch flushing
- [ ] Force flush on events (logout, shutdown)
- [ ] Cache metrics

**Day 8-9: Priority Mode**
- [ ] Priority scoring algorithm
- [ ] Cleanup strategy implementation
- [ ] Storage monitoring
- [ ] Auto-trigger on quota exceed

**Day 10: API Endpoints (Basic)**
- [ ] User endpoints: GET/POST/DELETE versions
- [ ] User endpoint: Priority toggle
- [ ] User endpoint: Restore version
- [ ] Admin endpoint: User settings CRUD

### Phase 2: Admin Features (Week 3)

**Day 11-12: Statistics & Monitoring**
- [ ] VCL stats service
- [ ] Real-time usage tracking
- [ ] Per-user statistics
- [ ] Cleanup job scheduling

**Day 13-14: Export System**
- [ ] ZIP export job queue
- [ ] Async export generation
- [ ] Temporary file management
- [ ] Download endpoint with streaming

**Day 15: Maintenance APIs**
- [ ] Manual cleanup endpoint
- [ ] Deduplication scan endpoint
- [ ] Blob orphan detection
- [ ] Admin version management

### Phase 3: Frontend Core (Week 4)

**Day 16-17: Settings Page**
- [ ] VCL Settings component
- [ ] Global settings form
- [ ] Per-user limits table
- [ ] Settings API integration

**Day 18-19: Stats Dashboard**
- [ ] Statistics widgets
- [ ] Storage charts (Chart.js/Recharts)
- [ ] User breakdown table
- [ ] Real-time updates (optional)

**Day 20: Database Page Integration**
- [ ] VCL tables in database view
- [ ] Special formatting for VCL data
- [ ] VCL dashboard widget
- [ ] Quick actions (export, cleanup)

### Phase 4: User Features (Week 5)

**Day 21-22: File Explorer Integration**
- [ ] Version indicator icons
- [ ] Priority star icons
- [ ] Context menu extension
- [ ] Tooltips and badges

**Day 23-24: Version History Modal**
- [ ] Version list component
- [ ] Version item design
- [ ] Download/Restore/Delete actions
- [ ] Quota bar
- [ ] Loading states

**Day 25: Diff Viewer**
- [ ] Diff API integration
- [ ] Unified diff display
- [ ] Side-by-side view (optional)
- [ ] Syntax highlighting for code

### Phase 5: Testing & Optimization (Week 6)

**Day 26-27: Unit Tests**
- [ ] VCLService tests
- [ ] Checksum tests
- [ ] Compression tests
- [ ] Deduplication tests
- [ ] Priority mode algorithm tests
- [ ] Caching mechanism tests

**Day 28-29: Integration Tests**
- [ ] API endpoint tests
- [ ] File upload → version creation flow
- [ ] Restore version flow
- [ ] Export ZIP generation
- [ ] Cleanup job execution

**Day 30: E2E Tests**
- [ ] Complete version lifecycle
- [ ] User quota enforcement
- [ ] Priority mode trigger
- [ ] Admin settings flow
- [ ] Export download flow

### Phase 6: Documentation & Deployment (Week 7)

**Day 31-32: Documentation**
- [ ] API documentation (OpenAPI/Swagger)
- [ ] User guide (how to use VCL)
- [ ] Admin guide (configuration)
- [ ] Developer docs (extending VCL)

**Day 33: Performance Optimization**
- [ ] Database query optimization
- [ ] Index tuning
- [ ] Caching strategy review
- [ ] Compression benchmark

**Day 34-35: Deployment & Monitoring**
- [ ] Production deployment checklist
- [ ] Monitoring setup (Grafana/Prometheus)
- [ ] Alert configuration
- [ ] Backup strategy for VCL data
- [ ] Rollback plan

---

## 🧪 Testing Strategy

### Unit Tests

#### Backend Services
```python
# tests/test_vcl_service.py

def test_should_create_version_respects_size_limit():
    file = create_test_file(size=101 * 1024 * 1024)  # 101 MB
    assert not should_create_version(file, "checksum")

def test_should_create_version_detects_unchanged_checksum():
    file = create_test_file()
    create_version(file, checksum="abc123")
    assert not should_create_version(file, "abc123")

def test_deduplication_reuses_existing_blob():
    content = b"test content"
    checksum = hashlib.sha256(content).hexdigest()
    
    blob1 = create_blob(content, checksum)
    blob2 = create_blob(content, checksum)
    
    assert blob1.id == blob2.id
    assert blob1.reference_count == 2

def test_compression_reduces_file_size():
    text_content = "hello world\n" * 1000
    original_size = len(text_content.encode())
    
    compressed_path = compress_and_store(text_content)
    compressed_size = Path(compressed_path).stat().st_size
    
    assert compressed_size < original_size * 0.5  # At least 50% reduction

def test_priority_mode_deletes_low_priority_first():
    # Create low priority versions
    low_priority_versions = [create_version(priority=False) for _ in range(5)]
    # Create high priority versions
    high_priority_versions = [create_version(priority=True) for _ in range(3)]
    
    # Trigger priority mode
    deleted = trigger_priority_mode(free_bytes=1024*1024)
    
    # Low priority should be deleted first
    assert all(v.id in deleted for v in low_priority_versions[:3])
    assert all(v.id not in deleted for v in high_priority_versions)

def test_caching_debounces_rapid_changes():
    file = create_test_file()
    
    # Simulate rapid changes
    for i in range(10):
        queue_version(file.id, f"content {i}".encode(), f"checksum{i}")
        await asyncio.sleep(0.1)
    
    # Wait for debounce window
    await asyncio.sleep(30)
    
    # Should only create 1 version (final state)
    versions = get_versions(file.id)
    assert len(versions) == 1
    assert versions[0].checksum == "checksum9"
```

#### Frontend Components
```typescript
// tests/components/VersionHistoryModal.test.tsx

describe('VersionHistoryModal', () => {
  it('renders version list correctly', () => {
    const versions = [
      { id: 1, version_number: 1, created_at: '2026-01-01' },
      { id: 2, version_number: 2, created_at: '2026-01-02' }
    ];
    
    render(<VersionHistoryModal fileId={1} fileName="test.txt" />);
    
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText('v2')).toBeInTheDocument();
  });
  
  it('allows restoring a version', async () => {
    const onRestore = jest.fn();
    render(<VersionHistoryModal ... />);
    
    const restoreButton = screen.getByLabelText('Restore version 1');
    await userEvent.click(restoreButton);
    
    expect(onRestore).toHaveBeenCalledWith(1);
  });
  
  it('shows diff when two versions selected', async () => {
    render(<VersionHistoryModal ... />);
    
    await userEvent.click(screen.getByTestId('version-1-compare'));
    await userEvent.click(screen.getByTestId('version-2-compare'));
    
    expect(screen.getByText('Diff View')).toBeInTheDocument();
  });
});
```

### Integration Tests

```python
# tests/integration/test_vcl_workflow.py

async def test_file_upload_creates_version(client, test_user):
    """Test: Datei-Upload erstellt automatisch Version"""
    # Upload file
    files = {'file': ('test.txt', b'test content', 'text/plain')}
    response = await client.post('/api/files/upload', files=files)
    file_id = response.json()['id']
    
    # Check version was created
    versions = await client.get(f'/api/files/{file_id}/versions')
    assert len(versions.json()['versions']) == 1
    assert versions.json()['versions'][0]['version_number'] == 1

async def test_overwrite_creates_new_version(client, test_file):
    """Test: Überschreiben erstellt neue Version"""
    # Upload modified content
    files = {'file': ('test.txt', b'modified content', 'text/plain')}
    response = await client.put(f'/api/files/{test_file.id}', files=files)
    
    # Check two versions exist
    versions = await client.get(f'/api/files/{test_file.id}/versions')
    assert len(versions.json()['versions']) == 2

async def test_quota_enforcement(client, test_user):
    """Test: Quota wird durchgesetzt"""
    # Set low quota
    await client.put(f'/api/admin/vcl/settings/{test_user.id}', json={
        'max_size_bytes': 1024  # 1 KB
    })
    
    # Try to upload large file
    large_content = b'x' * (2 * 1024)  # 2 KB
    files = {'file': ('large.txt', large_content, 'text/plain')}
    response = await client.post('/api/files/upload', files=files)
    
    assert response.status_code == 413  # Payload too large
    assert 'quota exceeded' in response.json()['detail'].lower()

async def test_export_generates_zip(client, admin_user, test_files_with_versions):
    """Test: Export generiert ZIP korrekt"""
    # Request export
    response = await client.post('/api/admin/vcl/export', json={
        'user_id': test_user.id,
        'include_metadata': True
    })
    export_id = response.json()['export_id']
    
    # Wait for export to complete
    await asyncio.sleep(2)
    
    # Download ZIP
    download = await client.get(f'/api/admin/vcl/export/{export_id}/download')
    assert download.status_code == 200
    assert download.headers['content-type'] == 'application/zip'
    
    # Verify ZIP contents
    zip_content = io.BytesIO(download.content)
    with zipfile.ZipFile(zip_content) as zf:
        assert 'manifest.json' in zf.namelist()
        assert any('metadata.json' in name for name in zf.namelist())
```

### E2E Tests

```typescript
// tests/e2e/vcl.spec.ts

describe('VCL End-to-End', () => {
  it('complete version lifecycle', async () => {
    await page.goto('/files');
    
    // Upload file
    await page.setInputFiles('input[type="file"]', 'test.txt');
    await page.click('button:has-text("Upload")');
    await expect(page.locator('.file-item:has-text("test.txt")')).toBeVisible();
    
    // Open file, modify, save (creates version)
    await page.click('.file-item:has-text("test.txt")');
    await page.click('button:has-text("Edit")');
    await page.fill('textarea', 'Modified content');
    await page.click('button:has-text("Save")');
    
    // Open version history
    await page.click('.file-item:has-text("test.txt")', { button: 'right' });
    await page.click('text=Version History');
    
    // Verify 2 versions exist
    await expect(page.locator('.version-item')).toHaveCount(2);
    
    // Restore to version 1
    await page.click('.version-item:has-text("v1") button:has-text("Restore")');
    await page.click('button:has-text("Confirm")');
    
    // Verify file content restored
    const content = await page.textContent('.file-content');
    expect(content).toBe('Original content');
  });
  
  it('admin can configure user quotas', async () => {
    await page.goto('/settings');
    await page.click('text=Version Control');
    
    // Find user row
    const userRow = page.locator('tr:has-text("john@example.com")');
    await userRow.click('button:has-text("Edit")');
    
    // Set quota
    await page.fill('input[name="max_size_bytes"]', '20');
    await page.selectOption('select', 'GB');
    await page.fill('input[name="depth"]', '10');
    await page.click('button:has-text("Save")');
    
    // Verify saved
    await expect(userRow.locator('text=20 GB')).toBeVisible();
    await expect(userRow.locator('text=Depth: 10')).toBeVisible();
  });
});
```

---

## 📊 Performance Benchmarks

### Expected Performance Metrics

#### Version Creation
- **Small files (<1 MB):** < 100ms
- **Medium files (1-10 MB):** < 500ms
- **Large files (10-100 MB):** < 5s
- **Compression overhead:** +10-30% (dependent on content)
- **Checksum calculation:** ~100 MB/s

#### Deduplication
- **Checksum lookup:** < 10ms (indexed)
- **Reference count update:** < 5ms
- **Storage savings:** 20-60% (dependent on duplicate rate)

#### Caching
- **Debounce window:** 30s (configurable)
- **Cache flush:** < 50ms
- **Memory overhead:** ~1 KB per pending change

#### Restore
- **Small files:** < 100ms
- **Large files:** < 2s
- **Decompression rate:** ~500 MB/s

#### Export
- **100 versions:** < 5s
- **1000 versions:** < 30s
- **10000 versions:** < 5min (background job)

---

## 🔒 Security Considerations

### Access Control
```python
def can_access_version(user: User, version: FileVersion) -> bool:
    """Check if user can access a specific version"""
    if user.role == 'admin':
        return True
    
    if version.user_id == user.id:
        return True
    
    # Check if file is shared with user
    file_permissions = get_file_permissions(version.file_id)
    if user.id in file_permissions.allowed_users:
        return True
    
    return False

def can_delete_version(user: User, version: FileVersion) -> bool:
    """Check if user can delete a version"""
    if user.role == 'admin':
        return True
    
    # Only owner can delete
    if version.user_id == user.id:
        # Cannot delete last version
        version_count = count_versions(version.file_id)
        return version_count > 1
    
    return False
```

### Audit Logging
Alle VCL-Operationen werden geloggt:
```python
# Version created
audit_log.create(
    user_id=user.id,
    action='vcl.version.create',
    resource_type='file_version',
    resource_id=version.id,
    details={
        'file_id': file.id,
        'version_number': version.version_number,
        'checksum': version.checksum,
        'was_cached': version.was_cached
    }
)

# Version restored
audit_log.create(
    user_id=user.id,
    action='vcl.version.restore',
    resource_type='file_version',
    resource_id=version.id,
    details={
        'file_id': file.id,
        'from_version': version.version_number,
        'to_version': new_version.version_number
    }
)

# Admin export
audit_log.create(
    user_id=admin.id,
    action='vcl.admin.export',
    resource_type='vcl_export',
    resource_id=export.id,
    details={
        'target_user_id': export.user_id,
        'file_count': export.file_count,
        'total_size': export.total_size
    }
)
```

### Data Protection
- Versionen werden mit gleichen Permissions wie Hauptdatei gespeichert
- Verschlüsselung: Wenn Hauptdatei verschlüsselt → Versionen auch
- Blobs sind nur via Version-Metadaten erreichbar (keine direkten Links)
- Export-ZIPs haben Ablaufdatum (24h)
- Temporary export files werden nach Download gelöscht

---

## 📈 Monitoring & Alerts

### Metrics to Track
```python
# Prometheus metrics
vcl_versions_total = Counter('vcl_versions_total', 'Total versions created')
vcl_versions_size_bytes = Gauge('vcl_versions_size_bytes', 'Total size of all versions')
vcl_compression_ratio = Gauge('vcl_compression_ratio', 'Average compression ratio')
vcl_dedup_savings_bytes = Gauge('vcl_dedup_savings_bytes', 'Bytes saved via deduplication')
vcl_cache_hits = Counter('vcl_cache_hits', 'Number of cache hits')
vcl_cache_flushes = Counter('vcl_cache_flushes', 'Number of cache flushes')
vcl_priority_mode_triggers = Counter('vcl_priority_mode_triggers', 'Priority mode activations')
vcl_cleanup_duration_seconds = Histogram('vcl_cleanup_duration_seconds', 'Cleanup job duration')
vcl_export_generation_seconds = Histogram('vcl_export_generation_seconds', 'Export generation time')
```

### Alert Rules
```yaml
# Grafana Alert Rules
- name: VCL Storage Critical
  condition: vcl_versions_size_bytes / vcl_settings_max_size_bytes > 0.95
  severity: critical
  notification: Email to admin
  
- name: VCL Priority Mode Frequent
  condition: rate(vcl_priority_mode_triggers[1h]) > 10
  severity: warning
  notification: Slack #ops-alerts
  
- name: VCL Cleanup Failed
  condition: vcl_cleanup_errors_total > 0
  severity: warning
  notification: PagerDuty
  
- name: VCL Export Slow
  condition: vcl_export_generation_seconds > 300
  severity: info
  notification: Slack #monitoring
```

### Health Checks
```python
async def vcl_health_check() -> Dict[str, Any]:
    """VCL system health check"""
    health = {
        'status': 'healthy',
        'checks': {}
    }
    
    # Check database connectivity
    try:
        version_count = db.query(FileVersion).count()
        health['checks']['database'] = 'ok'
    except Exception as e:
        health['status'] = 'degraded'
        health['checks']['database'] = f'failed: {e}'
    
    # Check storage availability
    try:
        storage_path = Path('storage/versions/blobs')
        if not storage_path.exists():
            raise Exception('Storage path not found')
        health['checks']['storage'] = 'ok'
    except Exception as e:
        health['status'] = 'unhealthy'
        health['checks']['storage'] = f'failed: {e}'
    
    # Check cache service
    try:
        pending_count = len(VCLCache.pending_changes)
        health['checks']['cache'] = f'ok ({pending_count} pending)'
    except Exception as e:
        health['status'] = 'degraded'
        health['checks']['cache'] = f'failed: {e}'
    
    # Check quota enforcement
    try:
        users_over_quota = count_users_over_quota()
        if users_over_quota > 0:
            health['checks']['quotas'] = f'warning ({users_over_quota} users over quota)'
        else:
            health['checks']['quotas'] = 'ok'
    except Exception as e:
        health['status'] = 'degraded'
        health['checks']['quotas'] = f'failed: {e}'
    
    return health
```

---

## 🎓 Best Practices Summary

### For Developers
1. **Always check checksums** before creating versions
2. **Use caching** for frequently modified files
3. **Enable compression** by default (huge savings)
4. **Implement deduplication** early (30-60% storage savings)
5. **Test priority mode** thoroughly (critical for stability)
6. **Log all operations** for debugging and audit
7. **Monitor performance** metrics continuously
8. **Set reasonable defaults** (depth=5, max_size=10GB)

### For Admins
1. **Start with conservative quotas** and increase as needed
2. **Monitor storage usage** weekly
3. **Run cleanup manually** before quota issues arise
4. **Export critical versions** regularly (backup strategy)
5. **Review priority mode triggers** monthly
6. **Adjust caching windows** based on user behavior
7. **Enable alerts** for storage >90%

### For Users
1. **Mark important files as high priority**
2. **Use version history** to recover from mistakes
3. **Download versions** before major changes
4. **Check quota usage** in version history modal
5. **Delete old versions** you don't need

---

## 📝 Deliverables Checklist

### Phase 1: Backend Core
- [x] Database migrations (4 tables)
- [x] VCL Service implementation
- [x] Checksum & compression utilities
- [x] Deduplication logic
- [x] Intelligent caching system
- [x] Priority mode algorithm
- [x] User/Admin API endpoints

### Phase 2: Admin Features
- [x] VCL statistics service
- [x] Per-user settings management
- [x] Export system (ZIP generation)
- [x] Maintenance APIs (cleanup, dedup)
- [x] Background job scheduling

### Phase 3: Frontend Core
- [x] Settings page VCL tab
- [x] VCL stats dashboard
- [x] Per-user limits management UI
- [x] Database page VCL integration

### Phase 4: User Features
- [x] File explorer version indicators
- [x] Context menu extensions
- [x] Version history modal
- [x] Diff viewer component
- [x] Restore/download/delete actions

### Phase 5: Testing & Docs
- [x] Unit tests (80%+ coverage)
- [x] Integration tests
- [x] E2E tests
- [x] API documentation
- [x] User guide
- [x] Admin guide

### Phase 6: Deployment
- [x] Production deployment plan
- [x] Monitoring setup
- [x] Alert configuration
- [x] Performance optimization
- [x] Backup strategy

---

## 🎉 Success Criteria

### Technical
- ✅ 100% of files <100MB are versioned automatically
- ✅ Compression achieves >50% average size reduction
- ✅ Deduplication saves >20% storage
- ✅ Priority mode prevents storage overflow
- ✅ Version creation <500ms for typical files
- ✅ Restore operation <2s for any file
- ✅ Zero data loss in all scenarios

### User Experience
- ✅ Users can restore any version in <10 seconds
- ✅ Diff viewer clearly shows changes
- ✅ Quota warnings appear before limit
- ✅ Export completes in <30s for typical users
- ✅ High priority files never deleted prematurely

### Business
- ✅ <5% support tickets related to VCL
- ✅ >80% user adoption (files with versions)
- ✅ Admin can manage all users from one page
- ✅ Storage costs reduced by 40% vs. naive versioning

---

## 🚧 Future Enhancements (Post-MVP)

1. **Advanced Diff Types**
   - Image diff (visual comparison)
   - Binary diff (hex viewer)
   - PDF diff (page-by-page)

2. **Version Comments & Tags**
   - User-added comments per version
   - Semantic versioning tags (v1.0, v2.0)
   - Version naming/labeling

3. **Collaborative Features**
   - Version merge conflicts resolution
   - Branch-like version trees
   - Shared version history across users

4. **ML-Powered Features**
   - Predict important versions (auto-priority)
   - Suggest cleanup opportunities
   - Detect significant changes automatically

5. **Advanced Storage**
   - S3-compatible external storage
   - Tiered storage (hot/cold)
   - CDN integration for downloads

6. **Enhanced Compression**
   - Delta compression (store diffs)
   - Content-aware compression (images, videos)
   - Adaptive compression levels

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-02  
**Author:** BaluHost Team  
**Status:** Ready for Implementation  

---

## 📞 Contact & Support

For questions or clarifications during implementation:
- **Technical Lead:** [Kontakt]
- **Project Manager:** [Kontakt]
- **Documentation:** `docs/VERSION_CONTROL_LIGHT.md`
- **Issue Tracker:** GitHub Issues with `vcl` label

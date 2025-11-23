# Storage Mountpoints / Drive Selector Feature

## Overview
The FileManager now displays RAID arrays and storage devices as root-level "drives" that users can select, similar to traditional file managers like Windows Explorer or macOS Finder.

## User Experience

### Drive Selector
- Located at the top of the FileManager page, above the breadcrumb navigation
- Shows all available storage mountpoints/drives
- Each drive displays:
  - **Icon**: 💾 for RAID, 🔧 for dev-storage, 💿 for other storage
  - **Name**: Human-readable name (e.g., "RAID1 Setup - md0", "Dev Storage")
  - **Usage**: Current used space / total capacity
  - **RAID Level**: If applicable (e.g., "RAID1")
  - **Status**: Visual warning if not optimal (⚠)

### Path Structure
Paths now include the mountpoint prefix:
- **Dev Mode**: `root\Dev Storage\images\photo.jpg`
- **RAID Arrays**: `root\RAID1 Setup - md0\documents\report.pdf`

### Behavior
- Selecting a different drive resets the current path to root
- Breadcrumb navigation starts from the selected drive
- Storage info (used/available) updates based on selected drive
- Files and folders are scoped to the selected mountpoint

## Technical Implementation

### Backend

#### New Endpoint: `/api/files/mountpoints`
**Method**: `GET`  
**Authentication**: Required (JWT)

**Response Schema** (`MountpointsResponse`):
```json
{
  "mountpoints": [
    {
      "id": "dev-storage",
      "name": "Dev Storage",
      "type": "dev-storage",
      "path": "",
      "size_bytes": 10737418240,
      "used_bytes": 2147483648,
      "available_bytes": 8589934592,
      "raid_level": null,
      "status": "optimal",
      "is_default": true
    },
    {
      "id": "md0",
      "name": "RAID1 Setup - md0",
      "type": "raid",
      "path": "/md0",
      "size_bytes": 5368709120,
      "used_bytes": 0,
      "available_bytes": 5368709120,
      "raid_level": "raid1",
      "status": "optimal",
      "is_default": false
    }
  ],
  "default_mountpoint": "dev-storage"
}
```

#### Schema: `StorageMountpoint`
Located in `backend/app/schemas/storage.py`

**Fields**:
- `id`: Unique identifier (e.g., "md0", "dev-storage")
- `name`: Display name
- `type`: Mountpoint type ("raid", "dev-storage", etc.)
- `path`: Path prefix for file operations
- `size_bytes`: Total capacity
- `used_bytes`: Currently used space
- `available_bytes`: Available space
- `raid_level`: RAID level if applicable (optional)
- `status`: Health status ("optimal", "degraded", "failed")
- `is_default`: Whether this is the default mountpoint

#### Dev Mode Behavior
In development mode (`NAS_MODE=dev`):
- Shows "Dev Storage" as the primary mountpoint
- Displays all configured RAID arrays from `raid.get_status()`
- Dev Storage uses existing `nas_quota_bytes` setting
- RAID arrays show full capacity with 0 usage (mock data)

#### Production Mode Behavior
In production mode:
- Lists all active RAID arrays from mdadm
- First array (md0) is marked as default
- TODO: Implement actual per-array usage tracking

### Frontend

#### Component: `FileManager.tsx`
**Location**: `client/src/pages/FileManager.tsx`

**New State**:
```typescript
const [mountpoints, setMountpoints] = useState<StorageMountpoint[]>([]);
const [selectedMountpoint, setSelectedMountpoint] = useState<StorageMountpoint | null>(null);
```

**Key Functions**:
- `loadMountpoints()`: Fetches available drives on component mount
- `loadFiles()`: Constructs full path with mountpoint prefix
- `loadStorageInfo()`: Uses mountpoint capacity directly

**Path Construction**:
```typescript
const fullPath = selectedMountpoint.type === 'dev-storage' 
  ? path  // Dev storage uses flat paths
  : `${selectedMountpoint.path}${path ? '/' + path : ''}`;  // RAID needs prefix
```

## User Stories

### 1. Browse Dev Storage
**As a** developer  
**I want to** see the dev-storage as a selectable drive  
**So that** I can browse my sandboxed development files

### 2. Switch Between RAID Arrays
**As a** user with multiple RAID arrays  
**I want to** switch between different storage arrays  
**So that** I can organize files across different storage pools

### 3. See Storage Capacity
**As a** user  
**I want to** see capacity and usage for each drive  
**So that** I can monitor storage utilization per array

## Future Enhancements

### Phase 2
- [ ] Per-array usage tracking in production mode
- [ ] Mount/unmount drives manually
- [ ] Show array health status in real-time
- [ ] Drag-and-drop files between arrays
- [ ] Default mountpoint preference setting

### Phase 3
- [ ] Network share mountpoints (SMB/NFS)
- [ ] Cloud storage integration (OneDrive, Google Drive)
- [ ] USB/External drive detection
- [ ] Hot-swap notification

## Testing

### Dev Mode Test Cases
1. ✅ Load mountpoints on FileManager mount
2. ✅ Display dev-storage as default
3. ✅ Show mock RAID arrays (md0, md1)
4. ✅ Switch between drives
5. ✅ Reset path when switching drives
6. ✅ Display correct capacity per drive

### Production Mode Test Cases
1. ⚠️ Load actual RAID arrays from mdadm
2. ⚠️ Handle degraded array status
3. ⚠️ Show usage for each array (TODO)
4. ⚠️ Handle array offline/failed states

## API Examples

### Get Mountpoints
```bash
curl -X GET http://localhost:8000/api/files/mountpoints \
  -H "Authorization: Bearer <token>"
```

### List Files on Specific Mountpoint
```bash
# Dev storage
curl -X GET "http://localhost:8000/api/files/list?path=images" \
  -H "Authorization: Bearer <token>"

# RAID array (production)
curl -X GET "http://localhost:8000/api/files/list?path=/md0/documents" \
  -H "Authorization: Bearer <token>"
```

## Configuration

### Backend Settings
No new configuration required. Uses existing:
- `NAS_MODE`: Determines dev vs production behavior
- `nas_quota_bytes`: Dev storage capacity limit

### Frontend
No configuration needed. Automatically adapts to backend response.

## Troubleshooting

### Issue: No mountpoints displayed
**Cause**: Backend not returning arrays  
**Solution**: Check RAID service status, ensure `get_status()` returns arrays

### Issue: Path not found after switching drives
**Cause**: Path construction mismatch  
**Solution**: Verify `path` construction in `loadFiles()` matches backend expectations

### Issue: Capacity shows 0 bytes
**Cause**: RAID backend not providing size data  
**Solution**: Check RAID array configuration, ensure size_bytes is calculated

## Related Documentation
- [RAID Setup Wizard](./RAID_SETUP_WIZARD.md)
- [Dev Mode](./DEV_CHECKLIST.md)
- [File Manager Features](./USER_GUIDE.md#file-manager)
- [API Reference](./API_REFERENCE.md)

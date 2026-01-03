# BaluDesk Feature Implementation Plan

## Aktueller Status ✅

### Bereits Implementiert (C++ Backend):
- ✅ **BaluhostClient**: Upload/Download File Methods vorhanden
- ✅ **IPC Handlers**: `handleUploadFile()`, `handleDownloadFile()` bereits implementiert
- ✅ **Sync Engine**: Komplettes Sync-System mit Database (sync_folders table)
- ✅ **IPC Handler**: `handleAddSyncFolder()` bereits vorhanden

### Frontend UI:
- ✅ Modern Dark Theme mit Gradient
- ✅ FileExplorer mit File-Liste
- ✅ Dashboard mit Sync Stats
- ✅ Toast Notification System (react-hot-toast)

---

## Feature 1: **Upload Files** 📤

### Backend (Bereits fertig):
- ✅ `BaluhostClient::uploadFile()` - Line 152 in baluhost_client.cpp
- ✅ `IpcServer::handleUploadFile()` - Line 615 in ipc_server_fixed.cpp
- ✅ IPC Message Type: `upload_file`

### Frontend (TODO):
1. **FileExplorer Upload Button** - Button existiert bereits, benötigt Implementierung
   - Electron Dialog für File-Auswahl (`dialog.showOpenDialog`)
   - IPC Call: `window.electronAPI.invoke('upload_file', { localPath, remotePath, mountId })`
   - Progress Tracking (optional für Sprint 2)
   - Toast Notification bei Success/Error

2. **Preload.ts Update**:
   - Electron Dialog API exposen
   - Upload IPC Wrapper

**Aufwand**: 2-3h

---

## Feature 2: **Download Files** 📥

### Backend (Bereits fertig):
- ✅ `BaluhostClient::downloadFile()` - Line 136 in baluhost_client.cpp
- ✅ `IpcServer::handleDownloadFile()` - Line 581 in ipc_server_fixed.cpp
- ✅ IPC Message Type: `download_file`

### Frontend (TODO):
1. **FileExplorer Download Button** - Placeholder existiert
   - Electron Dialog für Save-Location (`dialog.showSaveDialog`)
   - IPC Call: `window.electronAPI.invoke('download_file', { fileId, localPath })`
   - Progress Tracking (optional)
   - Toast Notification

2. **Preload.ts Update**:
   - Dialog API exposen

**Aufwand**: 2h

---

## Feature 3: **Add Sync Folders** 📁

### Backend (Bereits fertig):
- ✅ `IpcServer::handleAddSyncFolder()` - Line 182 in ipc_server_fixed.cpp
- ✅ `IpcServer::handleRemoveSyncFolder()` - Line 226
- ✅ `IpcServer::handleGetFolders()` - Line 317
- ✅ Database: `sync_folders` table mit allen Feldern
- ✅ IPC Message Types: `add_sync_folder`, `remove_sync_folder`, `get_folders`

### Frontend (TODO):
1. **Dashboard "Add Folder" Button Implementierung**:
   - Dialog für Local Folder Selection
   - Input für Remote Path
   - IPC Call: `window.electronAPI.invoke('add_sync_folder', { localPath, remotePath })`
   - Reload Folder List nach Success

2. **Sync Folder Management**:
   - Enable/Disable Toggle
   - Remove Folder Button
   - Status Indicator (Active/Paused)

3. **Preload.ts Update**:
   - Folder Selection Dialog API

**Aufwand**: 3-4h

---

## Feature 4: **Notification System** 🔔

### Backend (Bereits vorhanden):
- ✅ IPC Server kann Messages an Frontend pushen
- ✅ `sync_stats` Messages bereits implementiert
- ✅ Logger System vorhanden

### Frontend (Bereits teilweise vorhanden):
- ✅ `react-hot-toast` bereits integriert
- ✅ Error Toasts funktionieren

### Erweiterungen (TODO):
1. **Backend → Frontend Notifications**:
   - Upload/Download Progress Events
   - Sync Conflict Notifications
   - Sync Complete Events
   - Error Notifications

2. **Frontend Notification Center** (Optional):
   - Notification History
   - Click-to-action (z.B. "View Conflict")
   - Notification Settings

3. **System Tray Integration** (Optional):
   - Windows Notification API
   - Tray Icon mit Badge Counter

**Aufwand**: 2-3h (Basic), 5-6h (mit Notification Center)

---

## Implementierungs-Reihenfolge

### Sprint 1 (Heute - 4-6h):
1. ✅ **Download Files** - Am einfachsten, Backend fertig
2. ✅ **Upload Files** - Ähnlich wie Download
3. ⚠️ **Basic Notifications** - Toast bei Upload/Download Success

### Sprint 2 (Next Session - 4-6h):
4. **Add Sync Folders** - UI für Folder Management
5. **Advanced Notifications** - Progress, Conflicts
6. **Polish** - Loading States, Error Handling

---

## Technische Details

### Preload API Erweiterungen benötigt:
```typescript
// File System Dialogs
selectFile: () => Promise<string | null>
selectFolder: () => Promise<string | null>
selectSaveLocation: (defaultName: string) => Promise<string | null>

// Bereits vorhanden (verwenden):
invoke: (channel: string, data: any) => Promise<any>
onBackendMessage: (callback: (msg: any) => void) => void
```

### IPC Messages (Bereits definiert):
- `upload_file`: { localPath, remotePath, mountId }
- `download_file`: { fileId, localPath }
- `add_sync_folder`: { localPath, remotePath }
- `remove_sync_folder`: { folderId }
- `get_folders`: {}

### FileItem Interface (bereits definiert):
```typescript
interface FileItem {
  id: number;
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number;
  // ...
}
```

---

## Nächste Schritte

1. **Start mit Download** - Einfachste Implementierung
2. **Upload danach** - Ähnliche Struktur
3. **Sync Folders** - Komplexer wegen UI
4. **Notifications** - Am Ende für alle Features

**Gesamtaufwand**: 10-14 Stunden für alle 4 Features komplett


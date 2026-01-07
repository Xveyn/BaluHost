# BaluDesk Electron Integration Guide

## Overview
This document describes the Electron API integration needed for secure token storage in the BaluDesk desktop client. The web client (`client/` folder) requires access to the OS keyring via Electron's `safeStorage` API.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        BaluDesk Desktop App                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Electron Main Process (C++ Backend Bridge)                │  │
│  │                                                             │  │
│  │  • Exposes safeStorage API via contextBridge               │  │
│  │  • Uses Electron safeStorage or keytar npm package         │  │
│  │  • Provides IPC bridge for C++ backend commands            │  │
│  └─────────────────────────┬──────────────────────────────────┘  │
│                            │                                      │
│  ┌─────────────────────────▼──────────────────────────────────┐  │
│  │  Renderer Process (Web Client from client/)                │  │
│  │                                                             │  │
│  │  • Uses window.electron.safeStorage for token storage      │  │
│  │  • Calls window.electron.ipcRenderer for C++ backend       │  │
│  │  • Hybrid API access: local HTTP or IPC fallback           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

## Required Implementation

### 1. Install Dependencies

```bash
cd baludesk
npm install keytar  # For secure OS keyring access
```

**Alternative**: Use Electron's built-in `safeStorage` API (Electron 13+)

### 2. Main Process: Context Bridge Setup

Create or update `baludesk/electron/preload.ts` or `main.ts`:

```typescript
import { contextBridge, ipcRenderer, safeStorage } from 'electron';
import keytar from 'keytar';  // If using keytar instead of safeStorage

const SERVICE_NAME = 'BaluDesk';

// Expose safe storage API to renderer
contextBridge.exposeInMainWorld('electron', {
  // Safe Storage API
  safeStorage: {
    /**
     * Store a value securely in OS keyring
     * @param key - Storage key
     * @param value - Value to store
     */
    async setItem(key: string, value: string): Promise<void> {
      try {
        // Option A: Using Electron safeStorage (recommended)
        const encrypted = safeStorage.encryptString(value);
        await ipcRenderer.invoke('safeStorage:set', key, encrypted.toString('base64'));
        
        // Option B: Using keytar (more compatible with older Electron)
        // await keytar.setPassword(SERVICE_NAME, key, value);
      } catch (error) {
        console.error('[SafeStorage] setItem error:', error);
        throw new Error(`Failed to store ${key}`);
      }
    },

    /**
     * Retrieve a value from OS keyring
     * @param key - Storage key
     * @returns Decrypted value or null if not found
     */
    async getItem(key: string): Promise<string | null> {
      try {
        // Option A: Using Electron safeStorage
        const encrypted = await ipcRenderer.invoke('safeStorage:get', key);
        if (!encrypted) return null;
        return safeStorage.decryptString(Buffer.from(encrypted, 'base64'));
        
        // Option B: Using keytar
        // return await keytar.getPassword(SERVICE_NAME, key);
      } catch (error) {
        console.error('[SafeStorage] getItem error:', error);
        return null;
      }
    },

    /**
     * Delete a value from OS keyring
     * @param key - Storage key
     */
    async deleteItem(key: string): Promise<void> {
      try {
        // Option A: Using Electron safeStorage
        await ipcRenderer.invoke('safeStorage:delete', key);
        
        // Option B: Using keytar
        // await keytar.deletePassword(SERVICE_NAME, key);
      } catch (error) {
        console.error('[SafeStorage] deleteItem error:', error);
      }
    },

    /**
     * Check if a key exists in keyring
     * @param key - Storage key
     */
    async hasItem(key: string): Promise<boolean> {
      try {
        const value = await this.getItem(key);
        return value !== null;
      } catch (error) {
        return false;
      }
    }
  },

  // Existing IPC methods (keep as-is)
  ipcRenderer: {
    invoke: (channel: string, ...args: any[]) => ipcRenderer.invoke(channel, ...args),
    send: (channel: string, ...args: any[]) => ipcRenderer.send(channel, ...args),
    on: (channel: string, listener: (...args: any[]) => void) => {
      ipcRenderer.on(channel, (_event, ...args) => listener(...args));
    },
  },

  // Platform info
  platform: process.platform,
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron
  }
});
```

### 3. Main Process: IPC Handlers

In your Electron main process file (e.g., `main.ts`):

```typescript
import { app, BrowserWindow, ipcMain } from 'electron';
import * as fs from 'fs/promises';
import * as path from 'path';

const STORAGE_FILE = path.join(app.getPath('userData'), 'secure-storage.json');

// Simple file-based storage for encrypted tokens
// (In production, this should use OS keyring via keytar or safeStorage)
let secureStore: Record<string, string> = {};

async function loadSecureStore() {
  try {
    const data = await fs.readFile(STORAGE_FILE, 'utf-8');
    secureStore = JSON.parse(data);
  } catch (error) {
    console.log('[SafeStorage] No existing store, creating new one');
    secureStore = {};
  }
}

async function saveSecureStore() {
  await fs.writeFile(STORAGE_FILE, JSON.stringify(secureStore, null, 2));
}

// IPC handlers for safeStorage
ipcMain.handle('safeStorage:set', async (_event, key: string, value: string) => {
  secureStore[key] = value;
  await saveSecureStore();
});

ipcMain.handle('safeStorage:get', async (_event, key: string) => {
  return secureStore[key] || null;
});

ipcMain.handle('safeStorage:delete', async (_event, key: string) => {
  delete secureStore[key];
  await saveSecureStore();
});

// Initialize on app ready
app.whenReady().then(async () => {
  await loadSecureStore();
  // ... rest of app initialization
});
```

### 4. TypeScript Definitions (Already Created)

The web client already has type definitions in `client/src/types/electron.d.ts`:

```typescript
export interface SafeStorage {
  setItem(key: string, value: string): Promise<void>;
  getItem(key: string): Promise<string | null>;
  deleteItem(key: string): Promise<void>;
  hasItem(key: string): Promise<boolean>;
}

export interface ElectronAPI {
  safeStorage?: SafeStorage;
  ipcRenderer: IpcRenderer;
  platform: string;
  versions: { node: string; chrome: string; electron: string };
}

declare global {
  interface Window {
    electron: ElectronAPI;
  }
}
```

## Security Considerations

### 1. OS Keyring Storage
- **Windows**: Uses Windows Credential Manager
- **macOS**: Uses Keychain Access
- **Linux**: Uses libsecret or GNOME Keyring

### 2. Encryption at Rest
Tokens are encrypted before being stored:
```typescript
// Electron safeStorage uses AES-256-GCM on Windows/Linux
// On macOS, it uses the system keychain (already encrypted)
const encrypted = safeStorage.encryptString(token);
```

### 3. No Plaintext Storage
**NEVER** store JWT tokens in:
- localStorage (accessible via XSS)
- sessionStorage (accessible via XSS)
- File system without encryption (accessible by other processes)

### 4. Token Lifecycle
- **Storage**: Encrypted in OS keyring via safeStorage
- **Retrieval**: Decrypted only when needed
- **Cleanup**: Deleted on logout via `clearToken()`
- **Expiry**: JWT tokens have 15min TTL, auto-removed on 401

## Usage in Web Client

The web client (`client/src/lib/secureStore.ts`) already uses this API:

```typescript
import { secureStore } from '../lib/secureStore';

// Store token after login
await secureStore.storeToken('my-jwt-token', 'username');

// Retrieve token
const token = await secureStore.getToken();

// Check authentication
const isAuth = await secureStore.isAuthenticated();

// Clear on logout
await secureStore.clearToken();
```

The `localApi` module (`client/src/lib/localApi.ts`) automatically manages tokens:

```typescript
import { localApi } from '../lib/localApi';

// Login (stores token internally)
const result = await localApi.login('admin', 'password');

// All subsequent calls auto-inject token
const profiles = await localApi.getServerProfiles();

// Logout (clears token)
await localApi.logout();
```

## Testing Checklist

### Unit Tests
- [ ] `window.electron.safeStorage.setItem()` stores values
- [ ] `window.electron.safeStorage.getItem()` retrieves values
- [ ] `window.electron.safeStorage.deleteItem()` removes values
- [ ] `window.electron.safeStorage.hasItem()` returns correct boolean

### Integration Tests
- [ ] Login flow stores JWT in keyring
- [ ] Logout flow clears JWT from keyring
- [ ] Token survives app restart (persisted in OS keyring)
- [ ] Token expires after 15 minutes (401 response)
- [ ] Failed login doesn't leave stale tokens

### Manual Tests
1. **Login Test**
   - Start BaluDesk desktop app
   - Login as `admin` / `changeme`
   - Verify console shows `[SecureStore] Token stored securely via Electron safeStorage`
   - Check OS keyring (Windows Credential Manager / macOS Keychain)
   - Should see entry for `BaluDesk:baludesk_token`

2. **Persistence Test**
   - Login to BaluDesk
   - Close app
   - Reopen app
   - Verify still logged in (token loaded from keyring)

3. **Logout Test**
   - Login to BaluDesk
   - Logout
   - Verify console shows `[SecureStore] Token cleared`
   - Check OS keyring - token entry should be removed

4. **Token Expiry Test**
   - Login to BaluDesk
   - Wait 16 minutes (token expires after 15min)
   - Make API call
   - Verify 401 response
   - Verify automatic redirect to login screen

## Troubleshooting

### Issue: `window.electron is undefined`
**Cause**: Context bridge not set up or preload script not loaded

**Solution**:
```typescript
// In BrowserWindow creation
const mainWindow = new BrowserWindow({
  webPreferences: {
    preload: path.join(__dirname, 'preload.js'),
    contextIsolation: true,
    nodeIntegration: false  // NEVER enable this
  }
});
```

### Issue: Tokens not persisting across restarts
**Cause**: Not using OS keyring, storing in memory only

**Solution**: Verify IPC handlers save to file or use keytar

### Issue: `safeStorage is not available`
**Cause**: Electron version < 13 or Linux without libsecret

**Solution**: Use keytar as fallback:
```typescript
const hasElectronSafeStorage = 
  typeof safeStorage !== 'undefined' && 
  safeStorage.isEncryptionAvailable();

if (hasElectronSafeStorage) {
  // Use Electron safeStorage
} else {
  // Use keytar fallback
  const keytar = require('keytar');
}
```

### Issue: Linux "Cannot find libsecret"
**Cause**: Missing system dependencies

**Solution**:
```bash
# Debian/Ubuntu
sudo apt-get install libsecret-1-dev

# Fedora/RHEL
sudo dnf install libsecret-devel

# Arch
sudo pacman -S libsecret
```

## Production Deployment

### 1. Update .env Configuration

Backend `.env`:
```bash
# Enable localhost-only enforcement
enforce_local_only=true

# Disable public profile listing in production
allow_public_profile_list=false

# Use strong secret keys (generate with: openssl rand -hex 32)
SECRET_KEY=your-generated-secret-key-here
token_secret=your-generated-token-secret-here
```

### 2. Package BaluDesk with Electron Builder

```json
{
  "build": {
    "appId": "com.baluhost.baludesk",
    "productName": "BaluDesk",
    "directories": {
      "output": "dist"
    },
    "extraResources": [
      {
        "from": "backend/build/Release/",
        "to": "backend",
        "filter": ["*.exe", "*.dll"]
      }
    ],
    "files": [
      "dist/**/*",
      "node_modules/**/*",
      "package.json"
    ],
    "win": {
      "target": ["nsis", "portable"],
      "icon": "assets/icon.ico"
    },
    "linux": {
      "target": ["AppImage", "deb"],
      "icon": "assets/icon.png"
    }
  }
}
```

### 3. Sign the Application

**Windows**: Use code signing certificate
```bash
electron-builder --win --x64 --sign
```

**macOS**: Use Apple Developer certificate
```bash
electron-builder --mac --x64 --sign
```

## References

- [Electron safeStorage API](https://www.electronjs.org/docs/latest/api/safe-storage)
- [keytar npm package](https://www.npmjs.com/package/keytar)
- [Electron contextBridge](https://www.electronjs.org/docs/latest/api/context-bridge)
- [BaluDesk Option B Implementation](./OPTION_B_IMPLEMENTATION.md)
- [Client secureStore module](../client/src/lib/secureStore.ts)
- [Client localApi module](../client/src/lib/localApi.ts)

## Next Steps

1. ✅ Web client utility modules created (`secureStore.ts`, `localApi.ts`)
2. ✅ Login component updated with hybrid auth flow
3. ✅ TypeScript definitions created
4. ⏳ **Implement Electron preload/main process safeStorage bridge** (this document)
5. ⏳ Test E2E integration (login, token persistence, logout)
6. ⏳ Add Settings toggle for "Allow Direct Local Access"
7. ⏳ Update user documentation

---

**Status**: Web client implementation complete. Waiting for BaluDesk Electron integration.

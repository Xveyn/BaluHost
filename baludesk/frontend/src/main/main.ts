const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, dialog, safeStorage } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { pathToFileURL } = require('url');

// HTTP Server für packaged app (statt file:// URLs für React Router Kompatibilität)
let mainWindow = null;
let appServer = null;

function startAppServer(distPath) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let filePath = path.join(distPath, req.url === '/' ? 'index.html' : req.url);
      
      // Security: prevent directory traversal
      if (!filePath.startsWith(distPath)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
      }
      
      fs.readFile(filePath, (err, content) => {
        if (err) {
          // For SPA: serve index.html for all non-existent routes
          if (path.extname(filePath) === '') {
            fs.readFile(path.join(distPath, 'index.html'), (err, content) => {
              res.writeHead(200, { 'Content-Type': 'text/html' });
              res.end(content);
            });
          } else {
            res.writeHead(404);
            res.end('Not Found');
          }
        } else {
          const ext = path.extname(filePath);
          const contentType = {
            '.html': 'text/html',
            '.js': 'application/javascript',
            '.css': 'text/css',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
          }[ext] || 'text/plain';
          
          res.writeHead(200, { 
            'Content-Type': contentType,
            'Cache-Control': 'no-cache'
          });
          res.end(content);
        }
      });
    });

    server.listen(0, 'localhost', () => {
      const port = server.address().port;
      console.log('[AppServer] Listening on http://localhost:' + port);
      appServer = server;
      resolve('http://localhost:' + port);
    });
  });
}
let backendProcess = null;
let tray = null;
let isQuitting = false;

// Backend Process Management
function startBackend() {
  // Check if dist/index.html exists to determine if we're packaged
  // This must be consistent with createWindow() logic!
  const indexPath = path.join(app.getAppPath(), 'dist', 'index.html');
  const isDev = !fs.existsSync(indexPath) || !app.isPackaged;
  
  let backendPath: string;
  
  if (isDev) {
    // Development mode: backend is in the repo structure
    // app.getAppPath() = /baluhost/baludesk/frontend
    // We need to go to /baluhost/baludesk/backend/build/Release
    const repoRoot = path.resolve(app.getAppPath(), '..', '..');
    const debugPath = path.join(repoRoot, 'baludesk', 'backend', 'build', 'Debug', 'baludesk-backend.exe');
    const releasePath = path.join(repoRoot, 'baludesk', 'backend', 'build', 'Release', 'baludesk-backend.exe');

    // Prefer Debug build when available during development to match local builds
    if (fs.existsSync(debugPath)) {
      backendPath = debugPath;
      console.log('[Backend] Using debug backend at:', backendPath);
    } else {
      backendPath = releasePath;
      console.log('[Backend] Using release backend at:', backendPath);
    }
  } else {
    // Production mode: backend is in the installation directory
    backendPath = path.join(app.getAppPath(), 'backend', 'baludesk-backend.exe');
  }

  // Check if backend exists before starting
  if (!fs.existsSync(backendPath)) {
    console.warn('[Backend] Not found at:', backendPath);
    console.warn('[Backend] Running in UI-only mode');
    return;
  }

  console.log('Starting C++ backend:', backendPath);

  backendProcess = spawn(backendPath, [], {
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  if (backendProcess.stdout) {
    let buffer = '';
    
    backendProcess.stdout.on('data', (data) => {
      buffer += data.toString();
      
      // Try to parse complete JSON messages (line-delimited)
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep incomplete line in buffer
      
      for (const line of lines) {
        if (!line.trim()) continue;
        
        try {
          const jsonMsg = JSON.parse(line);
          console.log('[Backend Response]:', jsonMsg);
          
          // Check if this is a response to a pending request (check both 'id' and 'requestId')
          // Important: Use explicit check for 'id' !== undefined to handle id: 0
          const messageId = jsonMsg.id !== undefined ? jsonMsg.id : jsonMsg.requestId;
          
          console.log('[IPC] Looking for id:', messageId, 'in pending:', Array.from(pendingRequests.keys()));
          
          if (messageId !== undefined && pendingRequests.has(messageId)) {
            console.log('[IPC] ✅ Found pending request:', messageId, '- resolving promise');
            const resolver = pendingRequests.get(messageId);
            pendingRequests.delete(messageId);
            
            // Call the resolver (which could be a simple resolve or a renderer send)
            if (typeof resolver === 'function') {
              // Add the requestId field to match what the renderer expects
              const responseWithRequestId = { ...jsonMsg, requestId: messageId };
              resolver(responseWithRequestId);
            }
          } else {
            // It's an event, forward to renderer
            console.log('[IPC] No pending request found, forwarding as event');
            if (mainWindow) {
              mainWindow.webContents.send('backend-message', jsonMsg);
            }
          }
        } catch (e) {
          // Not JSON, just log
          console.log('[Backend]:', line);
        }
      }
    });
  }

  if (backendProcess.stderr) {
    backendProcess.stderr.on('data', (data) => {
      console.error('[Backend Error]:', data.toString());
    });
  }

  backendProcess.on('close', (code) => {
    console.log(`Backend process exited with code ${code}`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
}

function sendToBackend(message: any) {
  if (backendProcess && backendProcess.stdin) {
    const jsonMsg = JSON.stringify(message) + '\n';
    backendProcess.stdin.write(jsonMsg);
  }
}

// Window Management
function createWindow() {
  // Load window icon
  let iconPath = path.join(__dirname, '../../public/icon.png');
  let windowIcon;
  if (fs.existsSync(iconPath)) {
    windowIcon = nativeImage.createFromPath(iconPath);
  }

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    icon: windowIcon,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    frame: true,
    backgroundColor: '#0f172a',
    show: false,
  });

  // Hide menu bar
  mainWindow.removeMenu();

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // Load app
  // Check if dist/index.html exists to determine if we're packaged
  const indexPath = path.join(app.getAppPath(), 'dist', 'index.html');
  const distPath = path.join(app.getAppPath(), 'dist');
  const isDev = !app.isPackaged;
  
  console.log('[Main] isDev:', isDev);
  console.log('[Main] app.isPackaged:', app.isPackaged);
  console.log('[Main] app.getAppPath():', app.getAppPath());
  console.log('[Main] indexPath exists:', fs.existsSync(indexPath));
  
  if (isDev) {
    // Development mode: load from Vite dev server
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    // Production mode: start local HTTP server for dist/ files
    console.log('[Main] Loading from packaged app, starting HTTP server...');
    startAppServer(distPath).then((url) => {
      console.log('[Main] Loading from server:', url);
      mainWindow.loadURL(url);
    });
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Minimize to tray instead of close
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
}

// System Tray
function createTray() {
  // Try to use the tray-specific icon, fallback to main icon
  let iconPath = path.join(__dirname, '../../public/icon-tray.png');
  if (!fs.existsSync(iconPath)) {
    iconPath = path.join(__dirname, '../../public/icon.png');
  }
  
  const icon = nativeImage.createFromPath(iconPath);
  
  tray = new Tray(icon.resize({ width: 16, height: 16 }));
  
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show BaluDesk',
      click: () => {
        mainWindow?.show();
      },
    },
    {
      label: 'Sync Status',
      click: () => {
        sendToBackend({ type: 'get_sync_state' });
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('BaluDesk - Syncing...');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    mainWindow?.show();
  });
}

// IPC Handlers
const pendingRequests = new Map();
let requestId = 0;

ipcMain.handle('backend-command', async (_event, command) => {
  console.log('[IPC] Backend command:', command);
  
  if (!backendProcess) {
    return { error: 'Backend not running' };
  }
  
  return new Promise((resolve) => {
    const id = requestId++;
    const commandWithId = { ...command, id };
    
    // Store resolver
    pendingRequests.set(id, resolve);
    
    // Send to backend
    sendToBackend(commandWithId);
    
    // Timeout after 10 seconds
    setTimeout(() => {
      if (pendingRequests.has(id)) {
        pendingRequests.delete(id);
        resolve({ error: 'Backend timeout' });
      }
    }, 10000);
  });
});

// IPC Message Handler for Remote Servers feature
// This handles request/response of IPC messages with the backend
ipcMain.handle('ipc-message', async (_event, message: any) => {
  console.log('[IPC Main] Received message from renderer:', message);
  
  if (!backendProcess) {
    console.error('[IPC Main] Backend not running');
    return { 
      error: 'Backend not running',
      requestId: message.requestId 
    };
  }

  // Create a promise that resolves when the backend responds
  return new Promise<any>((resolve) => {
    const messageId = message.requestId;
    
    // Store the resolver
    const resolver = (response: any) => {
      console.log('[IPC Main] Got response, resolving:', response);
      // Make sure response has the requestId
      const responseWithId = { ...response, requestId: messageId };
      resolve(responseWithId);
    };
    
    pendingRequests.set(messageId, resolver);

    // Setup timeout
    const timeoutId = setTimeout(() => {
      if (pendingRequests.has(messageId)) {
        pendingRequests.delete(messageId);
        console.error('[IPC Main] ❌ Request timeout:', messageId);
        resolve({
          error: 'IPC request timeout',
          requestId: messageId
        });
      }
    }, 30000); // 30 second timeout

    // Send to backend
    console.log('[IPC Main] Forwarding to backend:', message);
    sendToBackend(message);
  });
});

ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

// Dialog handlers
ipcMain.handle('dialog:openFile', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'All Files', extensions: ['*'] }
    ]
  });
  
  if (result.canceled) {
    return null;
  }
  
  return result.filePaths[0] || null;
});

ipcMain.handle('dialog:openFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  
  if (result.canceled) {
    return null;
  }
  
  return result.filePaths[0] || null;
});

ipcMain.handle('dialog:saveFile', async (_event, defaultName: string) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultName,
    filters: [
      { name: 'All Files', extensions: ['*'] }
    ]
  });
  
  if (result.canceled) {
    return null;
  }
  
  return result.filePath || null;
});

// Settings Handlers
ipcMain.handle('settings:get', async () => {
  console.log('[IPC] Getting settings from backend');
  const id = requestId++;
  
  return new Promise<any>((resolve) => {
    const timeout = setTimeout(() => {
      console.error('[IPC] ❌ Settings get TIMEOUT - id:', id, 'still in map:', pendingRequests.has(id));
      if (pendingRequests.has(id)) {
        pendingRequests.delete(id);
      }
      resolve({ success: false, error: 'Settings request timeout' });
    }, 5000);
    
    // Register handler in pendingRequests
    pendingRequests.set(id, resolve);
    console.log('[IPC] Registered id in map:', id, 'Map size:', pendingRequests.size);
    
    console.log('[IPC] Sending get_settings to backend with id:', id);
    sendToBackend({ 
      type: 'get_settings',
      id
    });
  });
});

ipcMain.handle('settings:update', async (_event, settings: any) => {
  console.log('[IPC] Updating settings:', settings);
  const id = requestId++;
  
  return new Promise<any>((resolve) => {
    const timeout = setTimeout(() => {
      console.error('[IPC] ❌ Settings update TIMEOUT - id:', id, 'still in map:', pendingRequests.has(id));
      if (pendingRequests.has(id)) {
        pendingRequests.delete(id);
      }
      resolve({ success: false, error: 'Settings update timeout' });
    }, 5000);
    
    // Register handler in pendingRequests
    pendingRequests.set(id, resolve);
    console.log('[IPC] Registered id in map:', id, 'Map size:', pendingRequests.size);
    
    console.log('[IPC] Sending update_settings to backend with id:', id);
    sendToBackend({ 
      type: 'update_settings',
      data: settings,
      id 
    });
  });
});

// User Info Handler
ipcMain.handle('user:getInfo', async () => {
  console.log('[IPC] Getting user info from settings');
  
  try {
    // Get settings (which includes username)
    const settings = await (ipcMain as any).handle('settings:get', null);
    
    // Return user info with username from settings
    return {
      success: true,
      data: {
        id: settings.data?.username || 'user', // Use username as ID
        username: settings.data?.username || '',
        avatar_url: settings.data?.avatar_url
      }
    };
  } catch (error) {
    console.error('[IPC] Error getting user info:', error);
    return { success: false, error: 'Failed to get user info' };
  }
});

// ============================================================================
// Secure Storage Handlers (OS Keyring via Electron safeStorage)
// ============================================================================

// Store for encrypted data - uses file-based persistence
const STORAGE_FILE = path.join(app.getPath('userData'), 'secure-storage.json');
let secureStore: Record<string, string> = {};

// Load secure storage from disk
async function loadSecureStore() {
  try {
    if (fs.existsSync(STORAGE_FILE)) {
      const data = fs.readFileSync(STORAGE_FILE, 'utf-8');
      secureStore = JSON.parse(data);
      console.log('[SafeStorage] Loaded', Object.keys(secureStore).length, 'encrypted items');
    } else {
      console.log('[SafeStorage] No existing store, creating new one');
      secureStore = {};
    }
  } catch (error) {
    console.error('[SafeStorage] Error loading store:', error);
    secureStore = {};
  }
}

// Save secure storage to disk
async function saveSecureStore() {
  try {
    const dir = path.dirname(STORAGE_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(STORAGE_FILE, JSON.stringify(secureStore, null, 2));
    console.log('[SafeStorage] Saved', Object.keys(secureStore).length, 'encrypted items');
  } catch (error) {
    console.error('[SafeStorage] Error saving store:', error);
    throw error;
  }
}

// Check if safeStorage is available (requires Electron 13+)
function isSafeStorageAvailable(): boolean {
  try {
    return safeStorage && typeof safeStorage.isEncryptionAvailable === 'function' 
      && safeStorage.isEncryptionAvailable();
  } catch (error) {
    console.warn('[SafeStorage] safeStorage not available:', error);
    return false;
  }
}

// Set item in secure storage
ipcMain.handle('safeStorage:set', async (_event, key: string, value: string) => {
  try {
    console.log('[SafeStorage] Setting item:', key);
    
    if (!key || typeof key !== 'string') {
      throw new Error('Invalid key: must be a non-empty string');
    }
    
    if (!value || typeof value !== 'string') {
      throw new Error('Invalid value: must be a non-empty string');
    }
    
    // Encrypt using Electron's safeStorage if available
    if (isSafeStorageAvailable()) {
      const encrypted = safeStorage.encryptString(value);
      secureStore[key] = encrypted.toString('base64');
      console.log('[SafeStorage] ✓ Encrypted with OS keyring (AES-256-GCM)');
    } else {
      // Fallback: store plaintext (with warning)
      console.warn('[SafeStorage] ⚠️ safeStorage unavailable, storing plaintext (INSECURE)');
      secureStore[key] = Buffer.from(value).toString('base64');
    }
    
    await saveSecureStore();
    console.log('[SafeStorage] ✓ Item saved:', key);
  } catch (error) {
    console.error('[SafeStorage] Error setting item:', error);
    throw error;
  }
});

// Get item from secure storage
ipcMain.handle('safeStorage:get', async (_event, key: string) => {
  try {
    console.log('[SafeStorage] Getting item:', key);
    
    if (!key || typeof key !== 'string') {
      throw new Error('Invalid key: must be a non-empty string');
    }
    
    const encrypted = secureStore[key];
    if (!encrypted) {
      console.log('[SafeStorage] Item not found:', key);
      return null;
    }
    
    // Decrypt using Electron's safeStorage if available
    if (isSafeStorageAvailable()) {
      const buffer = Buffer.from(encrypted, 'base64');
      const decrypted = safeStorage.decryptString(buffer);
      console.log('[SafeStorage] ✓ Decrypted from OS keyring');
      return decrypted;
    } else {
      // Fallback: decode base64
      console.warn('[SafeStorage] ⚠️ safeStorage unavailable, decoding plaintext');
      return Buffer.from(encrypted, 'base64').toString('utf-8');
    }
  } catch (error) {
    console.error('[SafeStorage] Error getting item:', error);
    // Return null instead of throwing to avoid breaking auth flow
    return null;
  }
});

// Delete item from secure storage
ipcMain.handle('safeStorage:delete', async (_event, key: string) => {
  try {
    console.log('[SafeStorage] Deleting item:', key);
    
    if (!key || typeof key !== 'string') {
      throw new Error('Invalid key: must be a non-empty string');
    }
    
    delete secureStore[key];
    await saveSecureStore();
    console.log('[SafeStorage] ✓ Item deleted:', key);
  } catch (error) {
    console.error('[SafeStorage] Error deleting item:', error);
    throw error;
  }
});

// Check if item exists in secure storage
ipcMain.handle('safeStorage:has', async (_event, key: string) => {
  try {
    console.log('[SafeStorage] Checking if item exists:', key);
    
    if (!key || typeof key !== 'string') {
      throw new Error('Invalid key: must be a non-empty string');
    }
    
    const exists = key in secureStore;
    console.log('[SafeStorage] Item exists:', key, '→', exists);
    return exists;
  } catch (error) {
    console.error('[SafeStorage] Error checking item:', error);
    return false;
  }
});

// ============================================================================
// App Lifecycle
// ============================================================================
app.whenReady().then(async () => {
  // Load secure storage before creating window
  await loadSecureStore();
  
  createWindow();
  createTray();
  startBackend();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, dialog } = require('electron');
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
    backendPath = path.join(
      repoRoot,
      'baludesk',
      'backend',
      'build',
      'Release',
      'baludesk-backend.exe'
    );
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
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    frame: true,
    backgroundColor: '#0f172a',
    show: false,
  });

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
  const icon = nativeImage.createFromPath(
    path.join(__dirname, '../../public/icon.png')
  );
  
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

// App Lifecycle
app.whenReady().then(() => {
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

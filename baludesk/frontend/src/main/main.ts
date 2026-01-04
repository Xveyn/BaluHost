const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow = null;
let backendProcess = null;
let tray = null;
let isQuitting = false;

// Backend Process Management
function startBackend() {
  const backendPath = path.join(
    app.getAppPath(),
    '..',
    'backend',
    'build',
    'Release',
    'baludesk-backend.exe'
  );

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
          const requestId = jsonMsg.id !== undefined ? jsonMsg.id : jsonMsg.requestId;
          
          console.log('[IPC] Looking for id:', requestId, 'in pending:', Array.from(pendingRequests.keys()));
          
          if (requestId !== undefined && pendingRequests.has(requestId)) {
            console.log('[IPC] ✅ Found pending request:', requestId, '- resolving promise');
            const resolve = pendingRequests.get(requestId);
            pendingRequests.delete(requestId);
            resolve(jsonMsg);
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
  const isDev = !app.isPackaged;
  
  if (isDev) {
    // Development mode: load from Vite dev server
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    // Production mode: load from built files
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
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

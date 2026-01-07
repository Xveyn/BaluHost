const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // Send command to backend
  sendBackendCommand: (command: any) => ipcRenderer.invoke('backend-command', command),
  
  // Convenient invoke method for direct backend communication
  invoke: (type: string, data: any) => ipcRenderer.invoke('backend-command', { type, data }),
  
  // Listen to backend messages
  onBackendMessage: (callback: (message: any) => void) => {
    ipcRenderer.on('backend-message', (_event, message) => callback(message));
  },

  // IPC message handling for Remote Servers - Uses invoke (request/response)
  sendIPCMessage: (message: any) => ipcRenderer.invoke('ipc-message', message),

  // App info
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  // Remove listener
  removeBackendListener: () => {
    ipcRenderer.removeAllListeners('backend-message');
  },

  // File system dialogs
  selectFile: () => ipcRenderer.invoke('dialog:openFile'),
  selectFolder: (options?: any) => ipcRenderer.invoke('dialog:openFolder', options),
  selectSaveLocation: (defaultName: string) => ipcRenderer.invoke('dialog:saveFile', defaultName),

  // Settings management
  getSettings: () => ipcRenderer.invoke('settings:get'),
  updateSettings: (settings: any) => ipcRenderer.invoke('settings:update', settings),

  // User info
  getUserInfo: () => ipcRenderer.invoke('user:getInfo'),

  // Secure Storage API (OS Keyring)
  safeStorage: {
    setItem: (key: string, value: string) => ipcRenderer.invoke('safeStorage:set', key, value),
    getItem: (key: string) => ipcRenderer.invoke('safeStorage:get', key),
    deleteItem: (key: string) => ipcRenderer.invoke('safeStorage:delete', key),
    hasItem: (key: string) => ipcRenderer.invoke('safeStorage:has', key),
  },
});

// Type definitions for TypeScript
export interface SafeStorage {
  setItem: (key: string, value: string) => Promise<void>;
  getItem: (key: string) => Promise<string | null>;
  deleteItem: (key: string) => Promise<void>;
  hasItem: (key: string) => Promise<boolean>;
}

export interface ElectronAPI {
  sendBackendCommand: (command: any) => Promise<any>;
  invoke: (type: string, data: any) => Promise<any>;
  onBackendMessage: (callback: (message: any) => void) => void;
  getAppVersion: () => Promise<string>;
  removeBackendListener: () => void;
  selectFile: () => Promise<string | null>;
  selectFolder: (options?: any) => Promise<any>;
  selectSaveLocation: (defaultName: string) => Promise<string | null>;
  getSettings: () => Promise<any>;
  updateSettings: (settings: any) => Promise<any>;
  getUserInfo: () => Promise<any>;
  safeStorage: SafeStorage;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}

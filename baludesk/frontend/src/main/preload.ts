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

  // App info
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  // Remove listener
  removeBackendListener: () => {
    ipcRenderer.removeAllListeners('backend-message');
  },

  // File system dialogs
  selectFile: () => ipcRenderer.invoke('dialog:openFile'),
  selectFolder: () => ipcRenderer.invoke('dialog:openFolder'),
  selectSaveLocation: (defaultName: string) => ipcRenderer.invoke('dialog:saveFile', defaultName),
});

// Type definitions for TypeScript
export interface ElectronAPI {
  sendBackendCommand: (command: any) => Promise<any>;
  invoke: (type: string, data: any) => Promise<any>;
  onBackendMessage: (callback: (message: any) => void) => void;
  getAppVersion: () => Promise<string>;
  removeBackendListener: () => void;
  selectFile: () => Promise<string | null>;
  selectFolder: () => Promise<string | null>;
  selectSaveLocation: (defaultName: string) => Promise<string | null>;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}

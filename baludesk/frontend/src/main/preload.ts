const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // Send command to backend
  sendBackendCommand: (command: any) => ipcRenderer.invoke('backend-command', command),
  
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
});

// Type definitions for TypeScript
export interface ElectronAPI {
  sendBackendCommand: (command: any) => Promise<any>;
  onBackendMessage: (callback: (message: any) => void) => void;
  getAppVersion: () => Promise<string>;
  removeBackendListener: () => void;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}

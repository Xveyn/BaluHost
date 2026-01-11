/**
 * Global Type Definitions for Electron API
 * Matches the API exposed in preload.ts via contextBridge
 */

export interface SafeStorage {
  setItem: (key: string, value: string) => Promise<void>;
  getItem: (key: string) => Promise<string | null>;
  deleteItem: (key: string) => Promise<void>;
  hasItem: (key: string) => Promise<boolean>;
}

export interface ElectronAPI {
  // Backend commands
  sendBackendCommand: (command: any) => Promise<any>;
  invoke: (type: string, data: any) => Promise<any>;
  onBackendMessage: (callback: (message: any) => void) => void;
  removeBackendListener: () => void;
  
  // IPC message handling for Remote Servers
  sendIPCMessage: (message: any) => Promise<any>;
  
  // App info
  getAppVersion: () => Promise<string>;
  
  // File dialogs
  selectFile: () => Promise<string | null>;
  selectFolder: (options?: any) => Promise<any>;
  selectSaveLocation: (defaultName: string) => Promise<string | null>;
  
  // Settings
  getSettings: () => Promise<any>;
  updateSettings: (settings: any) => Promise<any>;
  
  // User info
  getUserInfo: () => Promise<any>;
  
  // Secure Storage (OS Keyring)
  safeStorage: SafeStorage;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}

export {};

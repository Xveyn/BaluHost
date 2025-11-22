// Mock data and utilities for development/testing
// Simulates Linux filesystem behavior on Windows

interface MockUser {
  id: string;
  username: string;
  email: string;
  password: string;
  role: 'admin' | 'user';
  quota: number; // in bytes
  usedSpace: number; // in bytes
}

interface MockSystemInfo {
  platform: string;
  totalStorage: number;
  usedStorage: number;
  freeStorage: number;
}

// Mock users database
export const mockUsers: MockUser[] = [
  {
    id: '1',
    username: 'admin',
    email: 'admin@baluhost.local',
    password: '', // Will be set by auth controller
    role: 'admin',
    quota: 10 * 1024 * 1024 * 1024, // 10GB
    usedSpace: 0
  }
];

// Mock system info for development
export const mockSystemInfo: MockSystemInfo = {
  platform: 'linux-mock',
  totalStorage: 10 * 1024 * 1024 * 1024, // 10GB total for testing
  usedStorage: 2 * 1024 * 1024 * 1024,    // 2GB used (simulated)
  freeStorage: 8 * 1024 * 1024 * 1024     // 8GB free
};

// Helper to check if we're in dev/mock mode
export const isDevelopmentMode = (): boolean => {
  return process.env.NODE_ENV === 'development' || process.platform !== 'linux';
};

// Mock storage calculation based on actual files in storage directory
export const calculateMockStorageUsage = async (storagePath: string): Promise<number> => {
  const fs = await import('fs/promises');
  const path = await import('path');
  
  let totalSize = 0;
  
  const calculateDirSize = async (dirPath: string): Promise<number> => {
    let size = 0;
    try {
      const entries = await fs.readdir(dirPath, { withFileTypes: true });
      
      for (const entry of entries) {
        const fullPath = path.join(dirPath, entry.name);
        if (entry.isDirectory()) {
          size += await calculateDirSize(fullPath);
        } else {
          const stats = await fs.stat(fullPath);
          size += stats.size;
        }
      }
    } catch (error) {
      // Directory might not exist yet
    }
    return size;
  };
  
  totalSize = await calculateDirSize(storagePath);
  return totalSize;
};

// Mock disk info (simulates df command on Linux)
export const getMockDiskInfo = async (storagePath: string) => {
  const usedStorage = await calculateMockStorageUsage(storagePath);
  const totalStorage = mockSystemInfo.totalStorage;
  const freeStorage = totalStorage - usedStorage;
  
  return {
    filesystem: 'mock-dev-storage',
    total: totalStorage,
    used: usedStorage,
    available: freeStorage,
    usePercent: `${Math.round((usedStorage / totalStorage) * 100)}%`,
    mountPoint: storagePath
  };
};

// Mock process list (simulates ps aux command)
export const getMockProcessList = () => {
  return [
    {
      user: 'root',
      pid: '1234',
      cpu: '2.5',
      mem: '1.2',
      command: 'node server/dist/index.js'
    },
    {
      user: 'www-data',
      pid: '5678',
      cpu: '0.8',
      mem: '0.5',
      command: 'nginx: worker process'
    },
    {
      user: 'baluhost',
      pid: '9012',
      cpu: '1.2',
      mem: '2.1',
      command: 'tsx watch src/index.ts'
    },
    {
      user: 'postgres',
      pid: '3456',
      cpu: '0.3',
      mem: '3.5',
      command: 'postgres: main process'
    }
  ];
};

// Check if user has enough quota
export const checkUserQuota = (userId: string, additionalSize: number): boolean => {
  const user = mockUsers.find(u => u.id === userId);
  if (!user) return false;
  
  return (user.usedSpace + additionalSize) <= user.quota;
};

// Update user's used space
export const updateUserSpace = (userId: string, sizeDelta: number): void => {
  const user = mockUsers.find(u => u.id === userId);
  if (user) {
    user.usedSpace += sizeDelta;
    if (user.usedSpace < 0) user.usedSpace = 0;
  }
};

// Format bytes to human readable
export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
};

// Generate mock file metadata
export const generateMockFileMetadata = (_filename: string) => {
  return {
    tags: [] as string[],
    description: '',
    shareLink: null,
    sharedAt: null,
    sharedBy: null
  };
};

export default {
  mockUsers,
  mockSystemInfo,
  isDevelopmentMode,
  calculateMockStorageUsage,
  getMockDiskInfo,
  getMockProcessList,
  checkUserQuota,
  updateUserSpace,
  formatBytes,
  generateMockFileMetadata
};

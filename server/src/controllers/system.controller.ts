import { Request, Response } from 'express';
import os from 'os';
import { exec } from 'child_process';
import { promisify } from 'util';
import { isDevelopmentMode, getMockDiskInfo, getMockProcessList } from '../utils/mockData';
import {
  getCpuHistory,
  getLatestCpuUsage,
  getLatestMemorySample,
  getMemoryHistory,
  getNetworkHistory
} from '../utils/telemetryMonitor.js';
import { SystemInfo } from '../types/index.js';

const execAsync = promisify(exec);

export const getSystemInfo = (_req: Request, res: Response): void => {
  try {
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const usedMem = totalMem - freeMem;

    const cpuUsage = getLatestCpuUsage();
    const latestMemory = getLatestMemorySample();

    const systemInfo: SystemInfo = {
      cpu: {
        usage: cpuUsage ?? (os.loadavg()[0] * 100) / os.cpus().length,
        cores: os.cpus().length
      },
      memory: {
        total: latestMemory?.total ?? totalMem,
        used: latestMemory?.used ?? usedMem,
        free: latestMemory ? latestMemory.total - latestMemory.used : freeMem
      },
      disk: {
        total: 0,
        used: 0,
        free: 0
      },
      uptime: os.uptime()
    };

    res.json(systemInfo);
  } catch (error) {
    res.status(500).json({ error: 'Failed to get system info' });
  }
};

export const getStorageInfo = async (_req: Request, res: Response): Promise<void> => {
  try {
    if (isDevelopmentMode()) {
      // Use mock data in development/Windows
      const storagePath = process.env.NAS_STORAGE_PATH || './storage';
      const mockDisk = await getMockDiskInfo(storagePath);
      res.json(mockDisk);
      console.log('✓ Mock storage info:', mockDisk.usePercent, 'used');
    } else if (process.platform === 'linux') {
      // For Linux production, use df command
      const { stdout } = await execAsync('df -B1 / | tail -1');
      const parts = stdout.trim().split(/\s+/);
      
      res.json({
        filesystem: parts[0],
        total: parseInt(parts[1]),
        used: parseInt(parts[2]),
        available: parseInt(parts[3]),
        usePercent: parts[4],
        mountPoint: parts[5]
      });
    } else {
      // Fallback
      res.json({
        message: 'Storage info only available on Linux systems',
        platform: process.platform
      });
    }
  } catch (error) {
    res.status(500).json({ error: 'Failed to get storage info' });
  }
};

export const getProcesses = async (_req: Request, res: Response): Promise<void> => {
  try {
    if (isDevelopmentMode()) {
      // Use mock data in development/Windows
      const processes = getMockProcessList();
      res.json({ processes });
      console.log('✓ Mock process list returned');
    } else if (process.platform === 'linux') {
      // For Linux production, use ps command
      const { stdout } = await execAsync('ps aux --sort=-%mem | head -20');
      const lines = stdout.trim().split('\n');
      const processes = lines.slice(1).map(line => {
        const parts = line.trim().split(/\s+/);
        return {
          user: parts[0],
          pid: parts[1],
          cpu: parts[2],
          mem: parts[3],
          command: parts.slice(10).join(' ')
        };
      });
      
      res.json({ processes });
    } else {
      // Fallback
      res.json({
        message: 'Process info only available on Linux systems',
        platform: process.platform
      });
    }
  } catch (error) {
    res.status(500).json({ error: 'Failed to get processes' });
  }
};

export const getTelemetryHistory = (_req: Request, res: Response): void => {
  res.json({
    cpu: getCpuHistory(),
    memory: getMemoryHistory(),
    network: getNetworkHistory()
  });
};

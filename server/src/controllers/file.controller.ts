import { Request, Response } from 'express';
import fs from 'fs/promises';
import path from 'path';
import { FileInfo } from '../types/index.js';

const NAS_STORAGE = path.resolve(process.env.NAS_STORAGE_PATH || './storage');

// Ensure storage directory exists
fs.mkdir(NAS_STORAGE, { recursive: true }).catch(console.error);

export const listFiles = async (req: Request, res: Response): Promise<void> => {
  try {
    const dirPath = req.query.path as string || '';
    const fullPath = path.resolve(path.join(NAS_STORAGE, dirPath));

    // Security check: prevent directory traversal
    if (!fullPath.startsWith(NAS_STORAGE)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const entries = await fs.readdir(fullPath, { withFileTypes: true });
    
    const files: FileInfo[] = await Promise.all(
      entries.map(async (entry) => {
        const entryPath = path.join(fullPath, entry.name);
        const stats = await fs.stat(entryPath);
        
        return {
          name: entry.name,
          path: path.relative(NAS_STORAGE, entryPath),
          size: stats.size,
          type: entry.isDirectory() ? 'directory' : 'file',
          mtime: stats.mtime
        };
      })
    );

    res.json({ files });
  } catch (error) {
    res.status(500).json({ error: 'Failed to list files' });
  }
};

export const downloadFile = async (req: Request, res: Response): Promise<void> => {
  try {
    const filePath = req.params.path as string;

    if (!filePath) {
      res.status(400).json({ error: 'File path is required' });
      return;
    }    const fullPath = path.join(NAS_STORAGE, filePath);

    // Security check
    if (!fullPath.startsWith(NAS_STORAGE)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const stats = await fs.stat(fullPath);
    if (!stats.isFile()) {
      res.status(400).json({ error: 'Not a file' });
      return;
    }

    res.download(fullPath);
  } catch (error) {
    res.status(500).json({ error: 'Failed to download file' });
  }
};

export const uploadFile = async (req: Request, res: Response): Promise<void> => {
  try {
    const targetPath = req.body.path || '';
    const files = req.files as Express.Multer.File[];

    if (!files || files.length === 0) {
      res.status(400).json({ error: 'No files provided' });
      return;
    }

    const fullTargetPath = path.join(NAS_STORAGE, targetPath);
    await fs.mkdir(fullTargetPath, { recursive: true });

    for (const file of files) {
      const destPath = path.join(fullTargetPath, file.originalname);
      await fs.rename(file.path, destPath);
    }

    res.json({ message: 'Files uploaded successfully', count: files.length });
  } catch (error) {
    res.status(500).json({ error: 'Failed to upload files' });
  }
};

export const deleteFile = async (req: Request, res: Response): Promise<void> => {
  try {
    const filePath = req.params.path as string;
    
    if (!filePath) {
      res.status(400).json({ error: 'File path is required' });
      return;
    }

    const fullPath = path.resolve(path.join(NAS_STORAGE, filePath));

    if (!fullPath.startsWith(NAS_STORAGE)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const stats = await fs.stat(fullPath);
    if (stats.isDirectory()) {
      await fs.rm(fullPath, { recursive: true });
    } else {
      await fs.unlink(fullPath);
    }

    res.json({ message: 'Deleted successfully' });
  } catch (error) {
    res.status(500).json({ error: 'Failed to delete file' });
  }
};

export const createFolder = async (req: Request, res: Response): Promise<void> => {
  try {
    const { path: parentPath, name } = req.body;
    
    if (!name) {
      res.status(400).json({ error: 'Folder name is required' });
      return;
    }

    const folderPath = parentPath ? path.join(parentPath, name) : name;
    const fullPath = path.resolve(path.join(NAS_STORAGE, folderPath));

    if (!fullPath.startsWith(NAS_STORAGE)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    await fs.mkdir(fullPath, { recursive: true });
    res.json({ message: 'Folder created successfully' });
  } catch (error) {
    res.status(500).json({ error: 'Failed to create folder' });
  }
};

export const renameFile = async (req: Request, res: Response): Promise<void> => {
  try {
    const { oldPath, newName } = req.body;
    
    if (!oldPath || !newName) {
      res.status(400).json({ error: 'Old path and new name are required' });
      return;
    }

    const fullOldPath = path.resolve(path.join(NAS_STORAGE, oldPath));
    const fullNewPath = path.resolve(path.join(path.dirname(fullOldPath), newName));

    if (!fullOldPath.startsWith(NAS_STORAGE) || !fullNewPath.startsWith(NAS_STORAGE)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    await fs.rename(fullOldPath, fullNewPath);
    res.json({ message: 'Renamed successfully' });
  } catch (error) {
    res.status(500).json({ error: 'Failed to rename file' });
  }
};

export const moveFile = async (req: Request, res: Response): Promise<void> => {
  try {
    const { sourcePath, targetPath } = req.body;
    
    if (!sourcePath || !targetPath) {
      res.status(400).json({ error: 'Source and target paths are required' });
      return;
    }

    const fullSourcePath = path.resolve(path.join(NAS_STORAGE, sourcePath));
    const fullTargetPath = path.resolve(path.join(NAS_STORAGE, targetPath));

    if (!fullSourcePath.startsWith(NAS_STORAGE) || !fullTargetPath.startsWith(NAS_STORAGE)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    await fs.mkdir(path.dirname(fullTargetPath), { recursive: true });
    await fs.rename(fullSourcePath, fullTargetPath);
    res.json({ message: 'Moved successfully' });
  } catch (error) {
    res.status(500).json({ error: 'Failed to move file' });
  }
};

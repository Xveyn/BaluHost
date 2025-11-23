import { Response } from 'express';
import fs from 'fs/promises';
import path from 'path';
import { AuthRequest, FileInfo } from '../types/index.js';
import {
  STORAGE_ROOT,
  clearPathMetadata,
  getOwnerId,
  movePathMetadata,
  setOwnerId,
  toPosixPath
} from '../utils/fileMetadata.js';
import { canAccess, ensureOwnerOrPrivileged, PermissionDeniedError } from '../utils/permissions.js';

// Ensure storage directory exists
fs.mkdir(STORAGE_ROOT, { recursive: true }).catch(console.error);

export const listFiles = async (req: AuthRequest, res: Response): Promise<void> => {
  try {
    const dirPath = req.query.path as string || '';
    const fullPath = path.resolve(path.join(STORAGE_ROOT, dirPath));

    // Security check: prevent directory traversal
    if (!fullPath.startsWith(STORAGE_ROOT)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const relativeDirPath = toPosixPath(path.relative(STORAGE_ROOT, fullPath));
    const dirOwnerId = await getOwnerId(relativeDirPath);
    if (!canAccess(req.user, dirOwnerId)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const entries = await fs.readdir(fullPath, { withFileTypes: true });
    
    const files: FileInfo[] = await Promise.all(
      entries.map(async (entry) => {
        const entryPath = path.join(fullPath, entry.name);
        const stats = await fs.stat(entryPath);
        const relativePath = toPosixPath(path.relative(STORAGE_ROOT, entryPath));
        const ownerId = await getOwnerId(relativePath);
        
        return {
          name: entry.name,
          path: relativePath,
          size: stats.size,
          type: entry.isDirectory() ? 'directory' : 'file',
          mtime: stats.mtime,
          ownerId
        };
      })
    );

    const visibleFiles = files.filter((item) => canAccess(req.user, item.ownerId));

    res.json({ files: visibleFiles });
  } catch (error) {
    res.status(500).json({ error: 'Failed to list files' });
  }
};

export const downloadFile = async (req: AuthRequest, res: Response): Promise<void> => {
  try {
    const filePath = req.params.path as string;

    if (!filePath) {
      res.status(400).json({ error: 'File path is required' });
      return;
    }
    const fullPath = path.join(STORAGE_ROOT, filePath);

    // Security check
    if (!fullPath.startsWith(STORAGE_ROOT)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const stats = await fs.stat(fullPath);
    if (!stats.isFile()) {
      res.status(400).json({ error: 'Not a file' });
      return;
    }

    const ownerId = await getOwnerId(toPosixPath(filePath));
    if (!canAccess(req.user, ownerId)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    res.download(fullPath);
  } catch (error) {
    res.status(500).json({ error: 'Failed to download file' });
  }
};

export const uploadFile = async (req: AuthRequest, res: Response): Promise<void> => {
  try {
    const targetPath = req.body.path || '';
    const files = req.files as Express.Multer.File[];

    if (!files || files.length === 0) {
      res.status(400).json({ error: 'No files provided' });
      return;
    }

    const normalizedTarget = toPosixPath(targetPath || '');
    if (normalizedTarget) {
      const targetOwnerId = await getOwnerId(normalizedTarget);
      ensureOwnerOrPrivileged(req.user, targetOwnerId);
    }

    const fullTargetPath = path.join(STORAGE_ROOT, targetPath);
    await fs.mkdir(fullTargetPath, { recursive: true });

    for (const file of files) {
      const destPath = path.join(fullTargetPath, file.originalname);
      await fs.rename(file.path, destPath);
      if (req.user?.id) {
        const relativeDest = toPosixPath(path.relative(STORAGE_ROOT, destPath));
        await setOwnerId(relativeDest, req.user.id);
      }
    }

    res.json({ message: 'Files uploaded successfully', count: files.length });
  } catch (error) {
    if (error instanceof PermissionDeniedError) {
      res.status(403).json({ error: error.message });
      return;
    }
    res.status(500).json({ error: 'Failed to upload files' });
  }
};

export const deleteFile = async (req: AuthRequest, res: Response): Promise<void> => {
  try {
    const filePath = req.params.path as string;
    
    if (!filePath) {
      res.status(400).json({ error: 'File path is required' });
      return;
    }

    const fullPath = path.resolve(path.join(STORAGE_ROOT, filePath));

    if (!fullPath.startsWith(STORAGE_ROOT)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const stats = await fs.stat(fullPath);
    const ownerId = await getOwnerId(toPosixPath(filePath));
    ensureOwnerOrPrivileged(req.user, ownerId);
    if (stats.isDirectory()) {
      await fs.rm(fullPath, { recursive: true });
    } else {
      await fs.unlink(fullPath);
    }

    await clearPathMetadata(toPosixPath(filePath));

    res.json({ message: 'Deleted successfully' });
  } catch (error) {
    if (error instanceof PermissionDeniedError) {
      res.status(403).json({ error: error.message });
      return;
    }
    res.status(500).json({ error: 'Failed to delete file' });
  }
};

export const createFolder = async (req: AuthRequest, res: Response): Promise<void> => {
  try {
    const { path: parentPath, name } = req.body;
    
    if (!name) {
      res.status(400).json({ error: 'Folder name is required' });
      return;
    }

    const folderPath = parentPath ? path.join(parentPath, name) : name;
    const fullPath = path.resolve(path.join(STORAGE_ROOT, folderPath));

    if (!fullPath.startsWith(STORAGE_ROOT)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const parentRelative = parentPath ? toPosixPath(parentPath) : '';
    if (parentRelative) {
      const parentOwnerId = await getOwnerId(parentRelative);
      ensureOwnerOrPrivileged(req.user, parentOwnerId);
    }

    await fs.mkdir(fullPath, { recursive: true });
    if (req.user?.id) {
      const relativeFolder = toPosixPath(path.relative(STORAGE_ROOT, fullPath));
      await setOwnerId(relativeFolder, req.user.id);
    }
    res.json({ message: 'Folder created successfully' });
  } catch (error) {
    if (error instanceof PermissionDeniedError) {
      res.status(403).json({ error: error.message });
      return;
    }
    res.status(500).json({ error: 'Failed to create folder' });
  }
};

export const renameFile = async (req: AuthRequest, res: Response): Promise<void> => {
  try {
    const { oldPath, newName } = req.body;
    
    if (!oldPath || !newName) {
      res.status(400).json({ error: 'Old path and new name are required' });
      return;
    }

    const fullOldPath = path.resolve(path.join(STORAGE_ROOT, oldPath));
    const fullNewPath = path.resolve(path.join(path.dirname(fullOldPath), newName));

    if (!fullOldPath.startsWith(STORAGE_ROOT) || !fullNewPath.startsWith(STORAGE_ROOT)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const ownerId = await getOwnerId(toPosixPath(oldPath));
    ensureOwnerOrPrivileged(req.user, ownerId);

    await fs.rename(fullOldPath, fullNewPath);
    const newRelative = toPosixPath(path.relative(STORAGE_ROOT, fullNewPath));
    await movePathMetadata(toPosixPath(oldPath), newRelative);
    res.json({ message: 'Renamed successfully' });
  } catch (error) {
    if (error instanceof PermissionDeniedError) {
      res.status(403).json({ error: error.message });
      return;
    }
    res.status(500).json({ error: 'Failed to rename file' });
  }
};

export const moveFile = async (req: AuthRequest, res: Response): Promise<void> => {
  try {
    const { sourcePath, targetPath } = req.body;
    
    if (!sourcePath || !targetPath) {
      res.status(400).json({ error: 'Source and target paths are required' });
      return;
    }

    const fullSourcePath = path.resolve(path.join(STORAGE_ROOT, sourcePath));
    const fullTargetPath = path.resolve(path.join(STORAGE_ROOT, targetPath));

    if (!fullSourcePath.startsWith(STORAGE_ROOT) || !fullTargetPath.startsWith(STORAGE_ROOT)) {
      res.status(403).json({ error: 'Access denied' });
      return;
    }

    const normalizedSource = toPosixPath(sourcePath);
    const sourceOwnerId = await getOwnerId(normalizedSource);
    ensureOwnerOrPrivileged(req.user, sourceOwnerId);

    const targetParent = path.dirname(fullTargetPath);
    const targetParentRelative = toPosixPath(path.relative(STORAGE_ROOT, targetParent));
    if (targetParentRelative) {
      const targetParentOwner = await getOwnerId(targetParentRelative);
      ensureOwnerOrPrivileged(req.user, targetParentOwner);
    }

    await fs.mkdir(targetParent, { recursive: true });
    await fs.rename(fullSourcePath, fullTargetPath);
    const newRelative = toPosixPath(path.relative(STORAGE_ROOT, fullTargetPath));
    await movePathMetadata(normalizedSource, newRelative);
    res.json({ message: 'Moved successfully' });
  } catch (error) {
    if (error instanceof PermissionDeniedError) {
      res.status(403).json({ error: error.message });
      return;
    }
    res.status(500).json({ error: 'Failed to move file' });
  }
};

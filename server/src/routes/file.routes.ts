import { Router } from 'express';
import { authMiddleware } from '../middleware/auth.middleware.js';
import * as fileController from '../controllers/file.controller.js';
import { uploadMiddleware } from '../middleware/upload.middleware.js';

const router = Router();

// All file routes require authentication
router.use(authMiddleware);

// File operations
router.get('/list', fileController.listFiles);
router.get('/download/:path(*)', fileController.downloadFile);
router.post('/upload', uploadMiddleware, fileController.uploadFile);
router.delete('/:path(*)', fileController.deleteFile);
router.post('/folder', fileController.createFolder);
router.put('/rename', fileController.renameFile);
router.put('/move', fileController.moveFile);

export default router;

import { Router } from 'express';
import { authMiddleware } from '../middleware/auth.middleware.js';
import * as systemController from '../controllers/system.controller.js';

const router = Router();

// All system routes require authentication
router.use(authMiddleware);

// System information
router.get('/info', systemController.getSystemInfo);
router.get('/storage', systemController.getStorageInfo);
router.get('/processes', systemController.getProcesses);
router.get('/telemetry/history', systemController.getTelemetryHistory);

export default router;

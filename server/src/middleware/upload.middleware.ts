import multer from 'multer';
import path from 'path';
import { Request } from 'express';

const storage = multer.diskStorage({
  destination: (_req: Request, _file: Express.Multer.File, cb) => {
    cb(null, process.env.NAS_TEMP_PATH || './uploads');
  },
  filename: (_req: Request, file: Express.Multer.File, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, file.fieldname + '-' + uniqueSuffix + path.extname(file.originalname));
  }
});

const upload = multer({
  storage,
  limits: {
    fileSize: parseInt(process.env.MAX_FILE_SIZE || '5368709120'), // 5GB default
    files: parseInt(process.env.MAX_FILES_PER_UPLOAD || '10')
  },
  fileFilter: (_req: Request, file: Express.Multer.File, cb) => {
    // Accept all files for NAS
    cb(null, true);
  }
});

export const uploadMiddleware = upload.array('files', 10);

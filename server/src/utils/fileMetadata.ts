import fs from 'fs/promises';
import path from 'path';

export interface FileMetadataEntry {
  ownerId?: string;
}

export const STORAGE_ROOT = path.resolve(process.env.NAS_STORAGE_PATH || './storage');
const METADATA_FILE = path.join(STORAGE_ROOT, '.metadata.json');

let ensurePromise: Promise<void> | null = null;

const normalizePath = (relativePath: string): string => {
  if (!relativePath) {
    return '';
  }
  const trimmed = relativePath.replace(/^\/+|\/+$/g, '');
  return trimmed.replace(/\\/g, '/');
};

const ensureMetadataReady = async (): Promise<void> => {
  if (!ensurePromise) {
    ensurePromise = (async () => {
      await fs.mkdir(STORAGE_ROOT, { recursive: true });
      try {
        await fs.access(METADATA_FILE);
      } catch {
        await fs.writeFile(METADATA_FILE, JSON.stringify({}, null, 2), 'utf-8');
      }
    })();
  }
  await ensurePromise;
};

const loadMetadata = async (): Promise<Record<string, FileMetadataEntry>> => {
  await ensureMetadataReady();
  try {
    const raw = await fs.readFile(METADATA_FILE, 'utf-8');
    const parsed = JSON.parse(raw) as Record<string, FileMetadataEntry>;
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch {}
  return {};
};

const saveMetadata = async (data: Record<string, FileMetadataEntry>): Promise<void> => {
  await ensureMetadataReady();
  await fs.writeFile(METADATA_FILE, JSON.stringify(data, null, 2), 'utf-8');
};

export const getOwnerId = async (relativePath: string): Promise<string | undefined> => {
  const key = normalizePath(relativePath);
  const data = await loadMetadata();
  return data[key]?.ownerId;
};

export const setOwnerId = async (relativePath: string, ownerId: string): Promise<void> => {
  const key = normalizePath(relativePath);
  const data = await loadMetadata();
  const entry = data[key] ?? {};
  entry.ownerId = ownerId;
  data[key] = entry;
  await saveMetadata(data);
};

export const clearPathMetadata = async (relativePath: string): Promise<void> => {
  const key = normalizePath(relativePath);
  const data = await loadMetadata();
  const removeKeys = Object.keys(data).filter((k) => k === key || k.startsWith(`${key}/`));
  for (const candidate of removeKeys) {
    delete data[candidate];
  }
  if (removeKeys.length > 0) {
    await saveMetadata(data);
  }
};

export const movePathMetadata = async (oldPath: string, newPath: string): Promise<void> => {
  const oldKey = normalizePath(oldPath);
  const newKey = normalizePath(newPath);
  if (oldKey === newKey) {
    return;
  }
  const data = await loadMetadata();
  const updates: Record<string, FileMetadataEntry> = {};
  let modified = false;
  for (const [key, value] of Object.entries(data)) {
    if (key === oldKey || key.startsWith(`${oldKey}/`)) {
      const suffix = key.slice(oldKey.length);
      const candidate = suffix ? `${newKey}${suffix}` : newKey;
      updates[candidate] = value;
      delete data[key];
      modified = true;
    }
  }
  if (modified) {
    Object.assign(data, updates);
    await saveMetadata(data);
  }
};

export const toPosixPath = (relativePath: string): string => normalizePath(relativePath);

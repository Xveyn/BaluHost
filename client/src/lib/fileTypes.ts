/**
 * File-type detection utilities.
 *
 * Canonical implementations -- every component that needs to detect
 * file types should import from here.
 */

export const getFileExtension = (filename: string): string => {
  return filename.split('.').pop()?.toLowerCase() || '';
};

export const isTextFile = (filename: string): boolean => {
  const ext = getFileExtension(filename);
  const textExtensions = ['txt', 'md', 'json', 'js', 'ts', 'jsx', 'tsx', 'css', 'html', 'xml', 'yaml', 'yml', 'log', 'py', 'java', 'c', 'cpp', 'h', 'cs', 'php', 'rb', 'go', 'rs', 'sh'];
  return textExtensions.includes(ext);
};

export const isImageFile = (filename: string): boolean => {
  const ext = getFileExtension(filename);
  return ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'].includes(ext);
};

export const isVideoFile = (filename: string): boolean => {
  const ext = getFileExtension(filename);
  return ['mp4', 'webm', 'ogg', 'mov', 'avi'].includes(ext);
};

export const isAudioFile = (filename: string): boolean => {
  const ext = getFileExtension(filename);
  return ['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(ext);
};

export const isPdfFile = (filename: string): boolean => {
  return getFileExtension(filename) === 'pdf';
};

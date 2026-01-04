/**
 * Validation utilities
 */

/**
 * Check if a string is empty or whitespace
 */
export const isEmpty = (str: string | null | undefined): boolean => {
  return !str || str.trim().length === 0;
};

/**
 * Check if a value is a valid number
 */
export const isValidNumber = (value: unknown): value is number => {
  return typeof value === 'number' && !isNaN(value);
};

/**
 * Check if an email is valid (basic validation)
 */
export const isValidEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

/**
 * Sanitize filename (remove invalid characters)
 */
export const sanitizeFilename = (filename: string): string => {
  return filename.replace(/[<>:"/\\|?*]/g, '');
};

/**
 * Check if a path is valid
 */
export const isValidPath = (path: string): boolean => {
  return path.length > 0 && (path === '/' || !path.endsWith('/'));
};

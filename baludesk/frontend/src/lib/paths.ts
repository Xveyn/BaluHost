/**
 * Path and navigation utilities
 */

/**
 * Join path segments with forward slashes
 */
export const joinPath = (...parts: string[]): string => {
  return parts
    .filter(Boolean)
    .join('/')
    .replace(/\/+/g, '/');
};

/**
 * Get the filename from a full path
 */
export const getFilename = (path: string): string => {
  return path.split('/').pop() || path;
};

/**
 * Get the directory path (everything except the filename)
 */
export const getDirectory = (path: string): string => {
  const parts = path.split('/');
  parts.pop();
  return '/' + parts.filter(Boolean).join('/');
};

/**
 * Get breadcrumb items from a path
 */
export interface BreadcrumbItem {
  name: string;
  path: string;
}

export const getBreadcrumbs = (currentPath: string): BreadcrumbItem[] => {
  const parts = currentPath.split('/').filter(Boolean);
  const breadcrumbs: BreadcrumbItem[] = [{ name: 'Root', path: '/' }];

  let path = '';
  for (const part of parts) {
    path += '/' + part;
    breadcrumbs.push({ name: part, path });
  }

  return breadcrumbs;
};

/**
 * Navigate to parent directory
 */
export const goToParent = (currentPath: string): string => {
  const parts = currentPath.split('/').filter(Boolean);
  parts.pop();
  return '/' + parts.join('/');
};

/**
 * Check if path is root
 */
export const isRoot = (path: string): boolean => {
  return path === '/';
};

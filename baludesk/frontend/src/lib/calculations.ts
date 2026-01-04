/**
 * Calculation utilities for common data operations
 */

/**
 * Calculate percentage of used to total
 */
export const calculatePercentage = (used: number, total: number): number => {
  if (!total || total === 0) return 0;
  return (used / total) * 100;
};

/**
 * Get memory usage percentage
 */
export interface MemoryInfo {
  used: number;
  total: number;
  available?: number;  // Optional - backend may send 'free' instead
  free?: number;       // Backend uses 'free' sometimes
}

export const getMemoryPercent = (memory: MemoryInfo): number => {
  return calculatePercentage(memory.used, memory.total);
};

/**
 * Get disk usage percentage
 */
export interface DiskInfo {
  used: number;
  total: number;
  available?: number;  // Optional - may not always be present
}

export const getDiskPercent = (disk: DiskInfo): number => {
  return calculatePercentage(disk.used, disk.total);
};

/**
 * Clamp a value between min and max
 */
export const clamp = (value: number, min: number, max: number): number => {
  return Math.min(Math.max(value, min), max);
};

/**
 * Get color based on percentage (for progress indicators)
 * Returns: 'green' for < 70%, 'yellow' for < 90%, 'red' for >= 90%
 */
export const getPercentageColor = (
  percentage: number
): 'green' | 'yellow' | 'red' => {
  if (percentage < 70) return 'green';
  if (percentage < 90) return 'yellow';
  return 'red';
};

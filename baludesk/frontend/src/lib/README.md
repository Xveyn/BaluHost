# Frontend Library Structure

This directory contains utility functions and helpers organized by functionality.

## Files

### `formatters.ts`
Formatting functions for common data types:
- `formatBytes()` - Convert bytes to human-readable size (B, KB, MB, GB, TB)
- `formatSize()` - Alternative formatting with simpler calculation
- `formatUptime()` - Convert seconds to human-readable uptime format
- `formatDate()` - Format ISO date strings to localized format
- `formatDateShort()` - Format to YYYY-MM-DD
- `formatTime()` - Format to time-only HH:MM:SS

### `calculations.ts`
Mathematical utilities and calculations:
- `calculatePercentage()` - Calculate percentage of used to total
- `getMemoryPercent()` - Get memory usage percentage
- `getDiskPercent()` - Get disk usage percentage
- `clamp()` - Clamp value between min and max
- `getPercentageColor()` - Get color indicator based on percentage

### `paths.ts`
Path and navigation utilities:
- `joinPath()` - Join path segments with forward slashes
- `getFilename()` - Extract filename from path
- `getDirectory()` - Get directory path without filename
- `getBreadcrumbs()` - Generate breadcrumb items from path
- `goToParent()` - Navigate to parent directory
- `isRoot()` - Check if path is root

### `validation.ts`
Data validation utilities:
- `isEmpty()` - Check if string is empty or whitespace
- `isValidNumber()` - Check if value is valid number
- `isValidEmail()` - Basic email validation
- `sanitizeFilename()` - Remove invalid characters from filename
- `isValidPath()` - Check if path is valid

### `index.ts`
Central export file - imports all utilities for convenient importing.

## Usage

```typescript
// Option 1: Import from index
import { formatBytes, formatSize, getBreadcrumbs } from '../../lib';

// Option 2: Import specific file
import { formatBytes } from '../../lib/formatters';
import { getBreadcrumbs } from '../../lib/paths';
```

## Best Practices

1. **Keep functions pure** - No side effects, same input = same output
2. **Add JSDoc comments** - Document all exported functions
3. **Use TypeScript** - Maintain type safety
4. **Single responsibility** - Each function does one thing
5. **Test functions** - Add unit tests in `__tests__` directory
6. **Export from index** - Make functions available from `lib/index.ts`

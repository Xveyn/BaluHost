import { useState, useCallback, useEffect } from 'react';
import { FileConflict, ConflictResolution, ConflictResolutionOption } from '../types';

// Type assertion for Electron API
declare const window: any;

interface UseConflictResolverReturn {
  conflicts: FileConflict[];
  isLoading: boolean;
  error: string | null;
  fetchConflicts: () => Promise<void>;
  resolveConflict: (resolution: ConflictResolution) => Promise<void>;
  resolveAllConflicts: (option: ConflictResolutionOption) => Promise<void>;
}

/**
 * Hook for managing file sync conflicts
 * Handles fetching conflicts from backend and resolving them
 */
export function useConflictResolver(): UseConflictResolverReturn {
  const [conflicts, setConflicts] = useState<FileConflict[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch conflicts from backend
  const fetchConflicts = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await window.electronAPI.sendBackendCommand({
        type: 'get_conflicts',
      });

      if (response.success) {
        const conflictList = response.data?.conflicts || [];
        setConflicts(conflictList);
      } else {
        throw new Error(response.error || 'Failed to fetch conflicts');
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      console.error('Failed to fetch conflicts:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Resolve individual conflict
  const resolveConflict = useCallback(
    async (resolution: ConflictResolution) => {
      setError(null);

      try {
        const response = await window.electronAPI.sendBackendCommand({
          type: 'resolve_conflict',
          data: resolution,
        });

        if (response.success) {
          // Remove resolved conflict from list
          setConflicts((prev) =>
            prev.filter((c) => c.id !== resolution.conflictId)
          );
        } else {
          throw new Error(response.error || 'Failed to resolve conflict');
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        setError(errorMsg);
        throw err;
      }
    },
    []
  );

  // Resolve all conflicts with the same option
  const resolveAllConflicts = useCallback(
    async (option: ConflictResolutionOption) => {
      setError(null);

      try {
        const response = await window.electronAPI.sendBackendCommand({
          type: 'resolve_all_conflicts',
          data: {
            resolution: option,
          },
        });

        if (response.success) {
          // Clear all conflicts
          setConflicts([]);
        } else {
          throw new Error(response.error || 'Failed to resolve conflicts');
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        setError(errorMsg);
        throw err;
      }
    },
    []
  );

  // Listen to backend messages for conflict updates
  useEffect(() => {
    const handleBackendMessage = (message: any) => {
      if (message.type === 'conflict_detected') {
        // Add new conflict to list
        setConflicts((prev) => [...prev, message.data]);
      } else if (message.type === 'conflicts_updated') {
        // Replace entire list
        setConflicts(message.data?.conflicts || []);
      }
    };

    window.electronAPI.onBackendMessage(handleBackendMessage);

    return () => {
      window.electronAPI.removeBackendListener();
    };
  }, []);

  return {
    conflicts,
    isLoading,
    error,
    fetchConflicts,
    resolveConflict,
    resolveAllConflicts,
  };
}

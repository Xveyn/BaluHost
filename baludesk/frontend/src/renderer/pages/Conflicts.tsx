import { useEffect } from 'react';
import toast from 'react-hot-toast';
import ConflictResolver from '../components/ConflictResolver';
import { useConflictResolver } from '../hooks/useConflictResolver';
import { ConflictResolution, ConflictResolutionOption } from '../types';

/**
 * Conflicts Page - Shows and handles file sync conflicts
 * Provides interface for resolving conflicts with different strategies
 */
export default function Conflicts() {
  const {
    conflicts,
    isLoading,
    error,
    fetchConflicts,
    resolveConflict,
    resolveAllConflicts,
  } = useConflictResolver();

  // Fetch conflicts on mount
  useEffect(() => {
    fetchConflicts();
  }, [fetchConflicts]);

  // Show error toast if any
  useEffect(() => {
    if (error) {
      toast.error(`Error: ${error}`);
    }
  }, [error]);

  const handleResolveConflict = async (resolution: ConflictResolution) => {
    try {
      await resolveConflict(resolution);
    } catch (err) {
      // Error is already handled by hook and displayed as toast
      throw err;
    }
  };

  const handleResolveAll = async (option: ConflictResolutionOption) => {
    try {
      await resolveAllConflicts(option);
    } catch (err) {
      // Error is already handled by hook and displayed as toast
      throw err;
    }
  };

  return (
    <div className="h-full bg-white dark:bg-gray-900">
      <ConflictResolver
        conflicts={conflicts}
        onResolveConflict={handleResolveConflict}
        onResolveAll={handleResolveAll}
        isLoading={isLoading}
      />
    </div>
  );
}

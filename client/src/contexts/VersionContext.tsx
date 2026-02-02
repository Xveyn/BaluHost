/**
 * Version Context for providing app version across the application
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import type { VersionInfo } from '../api/updates';
import { getPublicVersion } from '../api/updates';

interface VersionContextType {
  version: string | null;
  fullVersion: VersionInfo | null;
  loading: boolean;
  error: string | null;
}

const VersionContext = createContext<VersionContextType | undefined>(undefined);

interface VersionProviderProps {
  children: React.ReactNode;
}

export function VersionProvider({ children }: VersionProviderProps) {
  const [fullVersion, setFullVersion] = useState<VersionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadVersion = async () => {
      try {
        const versionInfo = await getPublicVersion();
        if (isMounted) {
          setFullVersion(versionInfo);
          setError(null);
        }
      } catch (err) {
        console.error('Failed to load version:', err);
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load version');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadVersion();

    return () => {
      isMounted = false;
    };
  }, []);

  const value: VersionContextType = {
    version: fullVersion?.version ?? null,
    fullVersion,
    loading,
    error,
  };

  return (
    <VersionContext.Provider value={value}>
      {children}
    </VersionContext.Provider>
  );
}

export function useVersion() {
  const context = useContext(VersionContext);
  if (context === undefined) {
    throw new Error('useVersion must be used within a VersionProvider');
  }
  return context;
}

/**
 * Hook to get formatted version string for display
 * Returns "v..." while loading, "v?.?.?" on error, or "v{version}" on success
 */
export function useFormattedVersion(prefix: string = 'BaluHost OS'): string {
  const { version, loading, error } = useVersion();

  if (loading) {
    return `${prefix} v...`;
  }

  if (error || !version) {
    return `${prefix} v?.?.?`;
  }

  return `${prefix} v${version}`;
}

import { useEffect, useState } from 'react';
import { fetchSmartStatus, type SmartStatusResponse } from '../api/smart';

const CACHE_KEY = 'smart_data_cache';
const CACHE_TIMESTAMP_KEY = 'smart_data_cache_timestamp';
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

function getCachedData(): SmartStatusResponse | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    const timestamp = localStorage.getItem(CACHE_TIMESTAMP_KEY);
    
    if (cached && timestamp) {
      const age = Date.now() - parseInt(timestamp);
      if (age < CACHE_DURATION) {
        return JSON.parse(cached);
      }
    }
  } catch (err) {
    console.error('Failed to read cache:', err);
  }
  return null;
}

function setCachedData(data: SmartStatusResponse): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
    localStorage.setItem(CACHE_TIMESTAMP_KEY, Date.now().toString());
  } catch (err) {
    console.error('Failed to write cache:', err);
  }
}

export function useSmartData(pollingInterval = 60000) {
  const cachedData = getCachedData();
  const [smartData, setSmartData] = useState<SmartStatusResponse | null>(cachedData);
  const [loading, setLoading] = useState(!cachedData);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = async () => {
    try {
      const data = await fetchSmartStatus();
      setSmartData(data);
      setCachedData(data);
      setError(null);
      setLastUpdated(new Date());
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden der SMART-Daten');
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    let timeoutId: number | undefined;

    const poll = () => {
      // Only fetch immediately if no cache
      if (!cachedData || !mounted) {
        fetchData();
      }
      timeoutId = window.setTimeout(poll, pollingInterval);
    };

    poll();

    return () => {
      mounted = false;
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    };
  }, [pollingInterval]);

  const refetch = () => {
    setLoading(true);
    fetchData();
  };

  return { smartData, loading, error, lastUpdated, refetch };
}

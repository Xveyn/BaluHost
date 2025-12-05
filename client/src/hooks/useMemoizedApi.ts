import { useRef } from "react";

const cache = new Map<string, any>();

export function useMemoizedApi<T = any>(url: string): T | undefined {
  const dataRef = useRef<T | undefined>(undefined);

  if (cache.has(url)) {
    dataRef.current = cache.get(url);
  } else {
    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        cache.set(url, data);
        dataRef.current = data;
      });
  }

  return dataRef.current;
}

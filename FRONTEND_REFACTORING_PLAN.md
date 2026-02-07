# BaluHost Frontend Refactoring Plan

## Zusammenfassung der Probleme

| Kategorie | Problem | Impact |
|-----------|---------|--------|
| **Kritisch** | `formatBytes()` 12x dupliziert | ~500 LOC redundant |
| **Kritisch** | `useMemoizedApi.ts` broken (Memory Leak, kein useEffect) | Potentielle Crashes |
| **Kritisch** | God Components (FileManager 1614 LOC, SystemMonitor 1438 LOC) | Schwer wartbar |
| **Hoch** | 118+ `any`-Types in catch-Blöcken | Type-Safety untergraben |
| **Hoch** | API Cache ohne Cleanup (`lib/api.ts`) | Memory Leak |
| **Mittel** | Interfaces mehrfach definiert (User, FileItem, StorageInfo) | Inkonsistenz |
| **Mittel** | Axios + Fetch gemischt | Inkonsistentes Error-Handling |

---

## Phase 1: Quick Wins (Tag 1)

### 1.1 Zentrale Utility-Funktionen erstellen
**NEU:** `client/src/utils/format.ts`
```typescript
export const formatBytes = (bytes: number, decimals = 2): string => {
  if (!bytes || !Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), units.length - 1);
  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(decimals)} ${units[i]}`;
};

export const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days}d ${hours}h ${minutes}m`;
};
```

**Danach ersetzen in 12 Dateien:**
- `pages/Dashboard.tsx` (Zeile 42)
- `pages/RaidManagement.tsx` (Zeile 25)
- `pages/AdminHealth.tsx` (Zeile 70)
- `pages/SystemMonitor.tsx` (Zeile 169)
- `pages/FileManager.tsx` (Zeile 353)
- `pages/Logging.tsx` (Zeile 71)
- `pages/SettingsPage.tsx` (Zeile 196)
- `components/RaidSetupWizard.tsx` (Zeile 74)
- `components/UploadProgressModal.tsx` (Zeile 30)
- `components/monitoring/HealthTab.tsx` (Zeile 73)
- `components/monitoring/LogsTab.tsx` (Zeile 76)
- `api/vcl.ts` (Zeile 180)

### 1.2 Broken Hook löschen
**LÖSCHEN:** `client/src/hooks/useMemoizedApi.ts`
- Wird nicht importiert (bereits verifiziert)
- Hat fundamentale React-Pattern-Verletzungen:
  - Kein `useEffect` → Fetch läuft auf jedem Render
  - Globaler Cache ohne Cleanup → Memory Leak
  - Keine Error-Behandlung
  - Keine Loading-States

### 1.3 Zentrale Types erstellen
**NEU:** `client/src/types/common.ts`
```typescript
export interface User {
  id: string;
  username: string;
  email: string;
  role: 'admin' | 'user';
}

export interface StorageInfo {
  totalBytes: number;
  usedBytes: number;
  availableBytes: number;
}

export interface FileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modifiedAt: string;
  ownerId?: number;
  ownerName?: string;
  file_id?: number;
}

export interface ApiError {
  error?: string;
  detail?: string;
  message?: string;
}
```

---

## Phase 2: Foundation (Tag 2-3)

### 2.1 Error Handler standardisieren
**NEU:** `client/src/utils/errorHandler.ts`
```typescript
import toast from 'react-hot-toast';
import type { ApiError } from '../types/common';

export const getErrorMessage = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  if (typeof error === 'object' && error !== null) {
    const apiError = error as ApiError;
    return apiError.detail ?? apiError.error ?? apiError.message ?? 'Unbekannter Fehler';
  }
  return 'Unbekannter Fehler';
};

export const handleApiError = (error: unknown, fallbackMessage: string): void => {
  const message = getErrorMessage(error);
  console.error(fallbackMessage, error);
  toast.error(`${fallbackMessage}: ${message}`);
};
```

**Dann schrittweise `catch (err: any)` ersetzen** - 53+ Dateien betroffen:
```typescript
// VORHER:
catch (err: any) {
  toast.error(err.response?.data?.detail || 'Failed');
}

// NACHHER:
catch (err) {
  handleApiError(err, 'Operation fehlgeschlagen');
}
```

### 2.2 API Response Interceptor
**UPDATE:** `client/src/lib/api.ts`
```typescript
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    const apiError: ApiError = {
      message: error.response?.data?.detail ?? error.message,
      error: error.response?.data?.error,
    };
    return Promise.reject(apiError);
  }
);
```

### 2.3 Cache Cleanup implementieren
**UPDATE:** `client/src/lib/api.ts`
```typescript
const MAX_CACHE_SIZE = 100;
const CLEANUP_INTERVAL = 60000; // 1 Minute

function cleanupExpiredCache(): void {
  const now = Date.now();
  for (const [key, entry] of apiCache.entries()) {
    if (entry.expires < now) {
      apiCache.delete(key);
    }
  }
  // LRU-artige Eviction wenn zu groß
  if (apiCache.size > MAX_CACHE_SIZE) {
    const entries = [...apiCache.entries()]
      .sort((a, b) => a[1].expires - b[1].expires);
    entries.slice(0, apiCache.size - MAX_CACHE_SIZE)
      .forEach(([key]) => apiCache.delete(key));
  }
}

// In main.tsx starten:
setInterval(cleanupExpiredCache, CLEANUP_INTERVAL);
```

### 2.4 ServiceCard memoizen
**UPDATE:** `client/src/components/services/ServiceCard.tsx`
```typescript
import { memo } from 'react';
// ... existing code ...
export default memo(ServiceCard);
```

---

## Phase 3: Component Refactoring (Tag 4-10)

### 3.1 FileManager.tsx aufteilen (1614 LOC → 6 Dateien)
**Neue Struktur:**
```
components/files/
├── FileViewer.tsx        # Zeilen 53-212 (bereits interne Funktion)
├── FileList.tsx          # Tabelle + Mobile View (Zeilen 1084-1475)
├── StorageSelector.tsx   # Mountpoint-Buttons (Zeilen 997-1031)
├── BreadcrumbNav.tsx     # Pfad-Navigation (Zeilen 1034-1058)
├── PermissionsModal.tsx  # Rechte-Dialog (Zeilen 1247-1344)
└── index.ts

hooks/useFileManager.ts   # State-Logik extrahieren (20+ useState)
```

**Custom Hook Beispiel:**
```typescript
// hooks/useFileManager.ts
export function useFileManager() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  // ... alle 20+ useState aus FileManager

  const loadFiles = useCallback(async (path: string) => { ... }, []);
  const handleUpload = useCallback(async (files: FileList) => { ... }, []);
  const handleDelete = useCallback(async (paths: string[]) => { ... }, []);

  return {
    state: { files, currentPath, loading, selectedFiles },
    actions: { loadFiles, handleUpload, handleDelete }
  };
}
```

### 3.2 SystemMonitor.tsx aufteilen (1438 LOC → Module)
**Bereits als interne Funktionen strukturiert** - nur extrahieren:
```
components/monitoring/
├── CpuTab.tsx
├── MemoryTab.tsx
├── NetworkTab.tsx
├── DiskIoTab.tsx
├── PowerTab.tsx
├── StatCard.tsx          # Zeilen 188-203
└── index.ts (aktualisieren)
```

**SystemMonitor.tsx bleibt als Container:**
```typescript
// pages/SystemMonitor.tsx (nach Refactoring ~100 LOC)
import { CpuTab, MemoryTab, NetworkTab, DiskIoTab, PowerTab } from '../components/monitoring';

export default function SystemMonitor() {
  const [activeTab, setActiveTab] = useState('cpu');

  return (
    <div>
      <TabNavigation active={activeTab} onChange={setActiveTab} />
      {activeTab === 'cpu' && <CpuTab />}
      {activeTab === 'memory' && <MemoryTab />}
      {/* ... */}
    </div>
  );
}
```

### 3.3 Dashboard.tsx modularisieren (758 LOC)
```
components/dashboard/
├── QuickStatsGrid.tsx     # Stats-Cards (CPU, RAM, Storage, Uptime)
├── SmartDrivesSection.tsx # SMART-Status der Festplatten
├── RaidStatusCard.tsx     # RAID-Widget
├── HealthChecks.tsx       # System-Health Checks
└── index.ts (aktualisieren)

hooks/useDashboardData.ts  # Polling-Logik konsolidieren
```

### 3.4 RaidManagement.tsx modularisieren (900 LOC)
```
components/raid/
├── RaidArrayCard.tsx      # Einzelnes Array anzeigen
├── DeviceTable.tsx        # Disk-Tabelle
├── DiskManagementSection.tsx
├── FormatDiskDialog.tsx
└── index.ts

hooks/useRaidManagement.ts # State-Logik
```

---

## Phase 4: Architecture (Optional, Woche 2+)

### 4.1 React Query einführen
**Installation:** `npm install @tanstack/react-query`

**Vorteile:**
- Automatisches Caching mit Invalidierung
- Request Deduplication
- Background Refetching
- Loading/Error States out-of-the-box

**Migration Beispiel:**
```typescript
// VORHER (useMonitoring.ts):
const [current, setCurrent] = useState(null);
const [loading, setLoading] = useState(true);
useEffect(() => { fetchData(); }, []);

// NACHHER:
import { useQuery } from '@tanstack/react-query';

export function useCpuMonitoring(options) {
  return useQuery({
    queryKey: ['cpu', 'current'],
    queryFn: getCpuCurrent,
    refetchInterval: options.pollInterval ?? 5000,
    staleTime: 2000,
  });
}
```

### 4.2 Error Boundaries
**NEU:** `client/src/components/common/ErrorBoundary.tsx`
```typescript
import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error boundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="p-6 bg-red-500/10 border border-red-500/30 rounded-lg">
          <h2 className="text-lg font-semibold text-red-200">
            Etwas ist schief gelaufen
          </h2>
          <p className="mt-2 text-sm text-red-300">{this.state.error?.message}</p>
          <button onClick={() => window.location.reload()} className="mt-4 btn btn-primary">
            Seite neu laden
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

### 4.3 Zustand für globales State
**Installation:** `npm install zustand`

```typescript
// store/userStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UserStore {
  user: User | null;
  token: string | null;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  logout: () => void;
}

export const useUserStore = create<UserStore>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setUser: (user) => set({ user }),
      setToken: (token) => set({ token }),
      logout: () => set({ user: null, token: null }),
    }),
    { name: 'user-store' }
  )
);
```

---

## Kritische Dateien

| Datei | Aktion | Priorität |
|-------|--------|-----------|
| `hooks/useMemoizedApi.ts` | LÖSCHEN | P1 |
| `lib/api.ts` | Cache-Fix + Interceptor | P1 |
| `pages/FileManager.tsx` | Aufteilen | P2 |
| `pages/SystemMonitor.tsx` | Aufteilen | P2 |
| `pages/Dashboard.tsx` | formatBytes + modularisieren | P2 |

---

## Empfohlene Reihenfolge

| Zeitraum | Tasks | Priorität |
|----------|-------|-----------|
| **Tag 1** | Phase 1 komplett (Quick Wins) | KRITISCH |
| **Tag 2-3** | Phase 2 (Foundation) | HOCH |
| **Tag 4-7** | Phase 3.1 + 3.2 (FileManager, SystemMonitor) | HOCH |
| **Tag 8-10** | Phase 3.3 + 3.4 (Dashboard, RaidManagement) | MITTEL |
| **Woche 2+** | Phase 4 (Optional: React Query, Zustand) | NIEDRIG |

---

## Verifikation

Nach jedem Schritt:
1. `npm run build` - TypeScript-Fehler prüfen
2. `npm run dev` - Manuelle Tests der betroffenen Seiten
3. Browser DevTools → Performance → keine Memory Leaks
4. Bestehende Funktionalität unverändert

---

## Risiko-Matrix

| Task | Risiko | Mitigation |
|------|--------|------------|
| formatBytes zentralisieren | Gering | Unit-Tests, Type-Checking |
| useMemoizedApi löschen | Gering | Grep nach Imports (keiner gefunden) |
| Error Handler | Mittel | Schrittweise Migration, einzeln testen |
| FileManager aufteilen | Hoch | Feature-Flags, alte Version als Fallback |
| React Query einführen | Hoch | Parallele Hooks behalten, schrittweise |

---

## Metriken (Vorher/Nachher)

| Metrik | Vorher | Nachher (geschätzt) |
|--------|--------|---------------------|
| Duplizierter Code | ~500 LOC | ~50 LOC |
| Größte Komponente | 1614 LOC | ~300 LOC |
| any-Types | 118+ | <20 |
| Memory Leaks | 3+ | 0 |
| Custom Hooks | 18 (inkonsistent) | 18 (standardisiert) |

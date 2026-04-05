# Upload-Fortschrittsverfolgung (SSE)

## Übersicht

Echtzeit-Upload-Fortschrittsverfolgung mittels Server-Sent Events (SSE) für Live-Feedback während Datei-Uploads.

## Architektur

### Backend-Komponenten

1. **Upload Progress Manager** (`backend/app/services/upload_progress.py`)
   - Verwaltet Upload-Sitzungen und Fortschrittsstatus
   - Handhabt SSE-Abonnements und Benachrichtigungen
   - Thread-sicher durch asyncio-Locks

2. **SSE-Endpoint** (`backend/app/api/routes/upload_progress.py`)
   - `/api/files/progress/{upload_id}` - SSE-Stream-Endpoint
   - Streamt Fortschrittsaktualisierungen an verbundene Clients
   - Schließt automatisch bei Abschluss/Fehler des Uploads

3. **Upload-Integration** (`backend/app/api/routes/files.py`)
   - Modifizierter `/api/files/upload`-Endpoint gibt `upload_ids` zurück
   - Erstellt Upload-Sitzungen vor der Dateiverarbeitung
   - Aktualisiert den Fortschritt während der Upload-Verarbeitung

### Frontend-Komponenten

1. **Upload Progress Library** (`client/src/lib/uploadProgress.ts`)
   - `UploadProgressStream` - SSE-Verbindung für einzelne Dateien
   - `UploadProgressManager` - Fortschrittsverwaltung für mehrere Dateien
   - Typsichere Interfaces für Fortschrittsdaten

2. **React Hooks** (`client/src/hooks/useUploadProgress.ts`)
   - `useUploadProgress` - Fortschrittsverfolgung für einzelne Dateien
   - `useMultiUploadProgress` - Mehrere Dateien mit aggregiertem Fortschritt
   - Automatische Bereinigung von Abonnements

3. **UI-Komponente** (`client/src/components/UploadProgressModal.tsx`)
   - Modal zur Anzeige des Echtzeit-Upload-Fortschritts
   - Individuelle Fortschrittsbalken pro Datei
   - Gesamtfortschrittsanzeige
   - Schließt automatisch bei Abschluss

## Verwendung

### Backend-API

#### Dateien mit Fortschrittsverfolgung hochladen

```http
POST /api/files/upload
Content-Type: multipart/form-data

{
  "files": [File, File, ...],
  "path": "destination/path"
}
```

**Antwort:**
```json
{
  "message": "Files uploaded",
  "uploaded": 2,
  "upload_ids": ["uuid-1", "uuid-2"]
}
```

#### Upload-Fortschritt abonnieren

```javascript
const eventSource = new EventSource('/api/files/progress/{upload_id}');

eventSource.addEventListener('progress', (event) => {
  const progress = JSON.parse(event.data);
  console.log(`${progress.filename}: ${progress.progress_percentage}%`);
});

eventSource.onerror = () => {
  console.error('Connection lost');
  eventSource.close();
};
```

### Frontend-Integration

#### Verwendung des Hooks

```typescript
import { useMultiUploadProgress } from '../hooks/useUploadProgress';

function MyComponent() {
  const [uploadIds, setUploadIds] = useState<string[] | null>(null);
  
  const {
    progressMap,
    overallPercentage,
    allCompleted
  } = useMultiUploadProgress(uploadIds);

  // Handle upload
  const handleUpload = async (files: FileList) => {
    const formData = new FormData();
    Array.from(files).forEach(file => {
      formData.append('files', file);
    });

    const response = await fetch('/api/files/upload', {
      method: 'POST',
      body: formData
    });

    const result = await response.json();
    setUploadIds(result.upload_ids); // Start progress tracking
  };

  return (
    <div>
      {uploadIds && (
        <div>
          Overall Progress: {overallPercentage.toFixed(1)}%
        </div>
      )}
    </div>
  );
}
```

#### Verwendung der Modal-Komponente

```typescript
import { UploadProgressModal } from '../components/UploadProgressModal';

function FileManager() {
  const [uploadIds, setUploadIds] = useState<string[] | null>(null);

  return (
    <div>
      {/* Your file manager UI */}
      
      {uploadIds && (
        <UploadProgressModal
          uploadIds={uploadIds}
          onClose={() => setUploadIds(null)}
        />
      )}
    </div>
  );
}
```

## Datenfluss

```
1. Client laedt Dateien hoch → POST /api/files/upload
2. Backend erstellt eine Upload-Sitzung pro Datei
3. Backend gibt upload_ids an den Client zurück
4. Client verbindet sich mit dem SSE-Endpoint für jede upload_id
5. Backend streamt Fortschrittsaktualisierungen während der Dateiverarbeitung
6. Client zeigt den Echtzeit-Fortschritt in der Benutzeroberfläche an
7. SSE-Verbindung wird bei Abschluss/Fehler geschlossen
8. Upload-Sitzung wird nach 60 Sekunden bereinigt
```

## Fortschrittsstatus

- **uploading**: Die Datei wird derzeit verarbeitet
- **completed**: Die Datei wurde erfolgreich hochgeladen
- **failed**: Der Upload ist fehlgeschlagen (inkl. Fehlermeldung)

## Fortschrittsdatenstruktur

```typescript
interface UploadProgress {
  upload_id: string;
  filename: string;
  total_bytes: number;
  uploaded_bytes: number;
  status: 'uploading' | 'completed' | 'failed';
  error?: string;
  started_at?: string;
  completed_at?: string;
  progress_percentage: number;
}
```

## Features

- **Echtzeit-Updates**: Live-Fortschritt mittels Server-Sent Events
- **Mehrere Dateien**: Gleichzeitige Verfolgung mehrerer Uploads
- **Aggregierter Fortschritt**: Gesamtfortschritt über alle Dateien
- **Fehlerbehandlung**: Fehlgeschlagene Uploads werden mit Fehlermeldungen gemeldet
- **Automatische Bereinigung**: Upload-Sitzungen laufen nach 60 Sekunden ab
- **Typsicher**: Vollständige TypeScript-Unterstützung im Frontend
- **Responsives UI**: Mobilfreundliches Fortschritts-Modal

## Tests

Backend-Tests ausführen:
```bash
cd backend
python -m pytest tests/test_upload_progress.py -v
```

## Konfiguration

### Bereinigungsverzögerung

Die Bereinigungsverzögerung kann in `upload_progress.py` angepasst werden:

```python
await self._cleanup_upload(upload_id, delay=60.0)  # 60 seconds default
```

### SSE-Keep-alive

Die SSE-Verbindung bleibt bestehen, bis der Upload abgeschlossen ist oder fehlschlaegt. Eine manuelle Keep-alive-Konfiguration ist nicht erforderlich.

## Browser-Kompatibilitaet

- Chrome/Edge 85+
- Firefox 80+
- Safari 14+
- IE wird nicht unterstützt (bei Bedarf EventSource-Polyfill verwenden)

## Hinweise zur Leistung

- SSE-Verbindungen sind leichtgewichtig (unidirektionales HTTP)
- Jeder Upload erstellt eine SSE-Verbindung
- Verbindungen werden bei Abschluss automatisch geschlossen
- Upload-Sitzungen werden nach 60 Sekunden bereinigt
- Speicherbedarf: ca. 1 KB pro aktivem Upload

## Fehlerbehebung

### SSE-Verbindung schlaegt fehl

Prüfen Sie die CORS-Konfiguration in `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Fortschritt wird nicht aktualisiert

1. Überprüfen Sie, ob `upload_ids` von `/api/files/upload` zurückgegeben werden
2. Prüfen Sie die Browser-Konsole auf SSE-Verbindungsfehler
3. Überprüfen Sie die Backend-Logs auf Fortschrittsaktualisierungen

### Speicherlecks

Upload-Sitzungen werden nach 60 Sekunden automatisch bereinigt. Bei Bedarf können Sie manuell aufraumen:

```typescript
import { getUploadProgressManager } from '../lib/uploadProgress';

const manager = getUploadProgressManager();
manager.closeAll(); // Close all active connections
```

## Implementierte Features

- [x] Chunked Upload mit automatischem Retry
- [x] Echtzeit-Fortschrittsanzeige via Server-Sent Events
- [x] Upload-Queue-Management

# Upload Progress Tracking (SSE)

## Overview

Real-time upload progress tracking using Server-Sent Events (SSE) to provide live feedback during file uploads.

## Architecture

### Backend Components

1. **Upload Progress Manager** (`backend/app/services/upload_progress.py`)
   - Manages upload sessions and progress state
   - Handles SSE subscriptions and notifications
   - Thread-safe with asyncio locks

2. **SSE Endpoint** (`backend/app/api/routes/upload_progress.py`)
   - `/api/files/progress/{upload_id}` - SSE stream endpoint
   - Streams progress updates to connected clients
   - Auto-closes on upload completion/failure

3. **Upload Integration** (`backend/app/api/routes/files.py`)
   - Modified `/api/files/upload` to return `upload_ids`
   - Creates upload sessions before processing files
   - Updates progress during upload processing

### Frontend Components

1. **Upload Progress Library** (`client/src/lib/uploadProgress.ts`)
   - `UploadProgressStream` - Single file SSE connection
   - `UploadProgressManager` - Multi-file progress management
   - Type-safe interfaces for progress data

2. **React Hooks** (`client/src/hooks/useUploadProgress.ts`)
   - `useUploadProgress` - Single file progress tracking
   - `useMultiUploadProgress` - Multiple files with aggregate progress
   - Automatic subscription cleanup

3. **UI Component** (`client/src/components/UploadProgressModal.tsx`)
   - Modal displaying real-time upload progress
   - Individual file progress bars
   - Overall progress indicator
   - Auto-closes on completion

## Usage

### Backend API

#### Upload Files with Progress Tracking

```http
POST /api/files/upload
Content-Type: multipart/form-data

{
  "files": [File, File, ...],
  "path": "destination/path"
}
```

**Response:**
```json
{
  "message": "Files uploaded",
  "uploaded": 2,
  "upload_ids": ["uuid-1", "uuid-2"]
}
```

#### Subscribe to Upload Progress

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

### Frontend Integration

#### Using the Hook

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

#### Using the Modal Component

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

## Data Flow

```
1. Client uploads files → POST /api/files/upload
2. Backend creates upload session for each file
3. Backend returns upload_ids to client
4. Client connects to SSE endpoint for each upload_id
5. Backend streams progress updates as files are processed
6. Client displays real-time progress in UI
7. SSE connection closes on completion/failure
8. Upload session cleaned up after 60s
```

## Progress States

- **uploading**: File is currently being processed
- **completed**: File uploaded successfully
- **failed**: Upload failed (includes error message)

## Progress Data Structure

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

✅ **Real-time Updates**: Live progress using Server-Sent Events  
✅ **Multi-file Support**: Track multiple uploads simultaneously  
✅ **Aggregate Progress**: Overall progress across all files  
✅ **Error Handling**: Failed uploads reported with error messages  
✅ **Auto-cleanup**: Upload sessions expire after 60 seconds  
✅ **Type-safe**: Full TypeScript support on frontend  
✅ **Responsive UI**: Mobile-friendly progress modal  

## Testing

Run backend tests:
```bash
cd backend
python -m pytest tests/test_upload_progress.py -v
```

## Configuration

### Cleanup Delay

Modify the cleanup delay in `upload_progress.py`:

```python
await self._cleanup_upload(upload_id, delay=60.0)  # 60 seconds default
```

### SSE Keep-alive

The SSE connection is kept alive until upload completion or failure. No manual keep-alive configuration needed.

## Browser Compatibility

✅ Chrome/Edge 85+  
✅ Firefox 80+  
✅ Safari 14+  
⚠️ IE Not supported (use EventSource polyfill if needed)

## Performance Considerations

- SSE connections are lightweight (one-way HTTP)
- Each upload creates one SSE connection
- Connections auto-close on completion
- Upload sessions are cleaned up after 60s
- Memory footprint: ~1KB per active upload

## Troubleshooting

### SSE Connection Fails

Check CORS configuration in `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Progress Not Updating

1. Verify `upload_ids` are returned from `/api/files/upload`
2. Check browser console for SSE connection errors
3. Verify backend logs for progress updates

### Memory Leaks

Upload sessions are automatically cleaned up after 60 seconds. If needed, manually clear:

```typescript
import { getUploadProgressManager } from '../lib/uploadProgress';

const manager = getUploadProgressManager();
manager.closeAll(); // Close all active connections
```

## Future Enhancements

- [ ] Upload pause/resume functionality
- [ ] Bandwidth throttling
- [ ] Upload queue management
- [ ] Progress persistence across page reloads
- [ ] Chunk-based upload with retry logic

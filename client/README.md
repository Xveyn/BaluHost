# BaluHost Frontend

Modern React TypeScript frontend for BaluHost NAS Management Platform.

## 🚀 Technology Stack

- **React 18** - Modern React with Hooks
- **TypeScript** - Type-safe development
- **Vite** - Fast build tool with HMR
- **Tailwind CSS** - Utility-first CSS framework
- **React Router** - Client-side routing
- **Recharts** - Data visualization
- **Axios** - HTTP client for API calls

## 📁 Project Structure

```
src/
├── api/                    # API client modules
│   ├── raid.ts            # RAID management API
│   ├── smart.ts           # SMART monitoring API
│   ├── logging.ts         # Audit logging API
│   └── shares.ts          # File sharing API
├── components/            # Reusable components
│   ├── Layout.tsx         # Main layout wrapper
│   └── ...
├── contexts/              # React contexts
│   └── ThemeContext.tsx   # Theme management
├── hooks/                 # Custom React hooks
│   ├── useSystemTelemetry.ts  # System metrics hook
│   └── useSmartData.ts        # SMART data hook
├── lib/                   # Utility libraries
│   └── api.ts             # Base API client
├── pages/                 # Page components
│   ├── Login.tsx          # Login page
│   ├── Dashboard.tsx      # Dashboard with live metrics
│   ├── FileManager.tsx    # File management
│   ├── UserManagement.tsx # User management (Admin)
│   ├── RaidManagement.tsx # RAID configuration
│   ├── SystemMonitor.tsx  # System monitoring
│   ├── Logging.tsx        # Audit logs
│   └── SettingsPage.tsx   # User settings
├── App.tsx                # Main app component
└── main.tsx               # Entry point
```

## 🎨 Features

### Authentication
- JWT token-based authentication
- Protected routes
- Role-based access control (Admin/User)
- Automatic token refresh

### Dashboard
- Real-time system metrics (CPU, RAM, Network)
- Live charts with Recharts
- Storage overview with quota visualization
- RAID status monitoring
- SMART disk health indicators

### File Manager
- Drag & drop file upload
- Multi-file upload support
- File preview (images, videos, PDFs, text)
- Folder navigation with breadcrumbs
- File operations (create, rename, move, delete)
- File sharing with public links
- Granular file permissions

### User Management (Admin)
- User CRUD operations
- Role assignment (Admin/User)
- User activity tracking
- Quota management

### RAID Management (Admin)
- RAID array status monitoring
- Disk health visualization
- Array creation wizard
- Degraded/rebuild simulation (Dev mode)
- SMART data integration

### System Monitor
- Live telemetry charts
- Disk I/O monitoring
- Process list
- Network statistics
- Historical data visualization

### Settings
- User profile management
- Password change
- Theme selection (prepared for future)
- Storage quota overview
- Activity log viewing

## 🛠️ Development

### Prerequisites
```bash
node >= 18.0.0
npm >= 9.0.0
```

### Installation
```bash
cd client
npm install
```

### Configuration
Create `.env` file (optional):
```env
VITE_API_BASE_URL=http://localhost:3001
```

### Start Development Server
```bash
npm run dev
```

App runs at `http://localhost:5173`

### Build for Production
```bash
npm run build
```

Output in `dist/` directory

### Preview Production Build
```bash
npm run preview
```

## 🎨 Styling

### Tailwind CSS
- Utility-first CSS framework
- Custom configuration in `tailwind.config.js`
- Dark theme by default
- Glassmorphism effects
- Responsive design

### Design System
- **Colors**: Purple primary, dark backgrounds
- **Typography**: System fonts for optimal rendering
- **Components**: Consistent button, card, and form styles
- **Icons**: Heroicons for UI elements

## 📡 API Integration

### Base API Client
Located in `src/lib/api.ts`:
- Axios instance with base URL
- Automatic JWT token injection
- Request/response interceptors
- Error handling

### API Modules
Specialized API clients in `src/api/`:
- `raid.ts` - RAID management endpoints
- `smart.ts` - SMART monitoring endpoints
- `logging.ts` - Audit log endpoints
- `shares.ts` - File sharing endpoints

### Example Usage
```typescript
import { api } from '@/lib/api';

// Get system info
const response = await api.get('/system/info');

// Upload file
const formData = new FormData();
formData.append('file', file);
await api.post('/files/upload', formData);
```

## 🔧 Custom Hooks

### useSystemTelemetry
Real-time system metrics with auto-refresh:
```typescript
const { telemetry, loading, error } = useSystemTelemetry(5000); // 5s interval
```

### useSmartData
SMART disk health monitoring:
```typescript
const { smartData, loading, error } = useSmartData();
```

## 🧪 Testing

### Run Tests
```bash
npm run test
```

### Linting
```bash
npm run lint
```

### Type Checking
```bash
npm run type-check
```

## 🚀 Deployment

### Production Build
```bash
npm run build
```

### Serve with Nginx
```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /path/to/client/dist;
    index index.html;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://localhost:3001;
    }
}
```

## 📚 Documentation

- **Main README**: `../README.md`
- **Technical Docs**: `../TECHNICAL_DOCUMENTATION.md`
- **API Reference**: `../docs/API_REFERENCE.md`
- **User Guide**: `../docs/USER_GUIDE.md`

## 🤝 Contributing

See `../CONTRIBUTING.md` for guidelines.

## 📄 License

See `../LICENSE` for details.

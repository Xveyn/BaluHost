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
- **i18n** - Internationalization support

## 📁 Project Structure

```
src/
├── api/                    # API client modules
│   ├── backup.ts          # Backup API
│   ├── benchmark.ts       # Benchmark API
│   ├── cloud-import.ts    # Cloud import API
│   ├── devices.ts         # Device management API
│   ├── energy.ts          # Energy monitoring API
│   ├── fan-control.ts     # Fan control API
│   ├── logging.ts         # Audit logging API
│   ├── monitoring.ts      # System monitoring API
│   ├── notifications.ts   # Notifications API
│   ├── plugins.ts         # Plugins API
│   ├── power-management.ts # Power management API
│   ├── power.ts           # Power API
│   ├── raid.ts            # RAID management API
│   ├── remote-servers.ts  # Remote servers API
│   ├── samba.ts           # Samba shares API
│   ├── schedulers.ts      # Scheduler API
│   ├── service-status.ts  # Service status API
│   ├── shares.ts          # File sharing API
│   ├── smart.ts           # SMART monitoring API
│   ├── ssd-cache.ts       # SSD cache API
│   ├── sync-schedules.ts  # Sync schedules API
│   ├── system.ts          # System API
│   ├── two-factor.ts      # 2FA API
│   ├── updates.ts         # Updates API
│   ├── users.ts           # Users API
│   ├── vcl.ts             # VCL (Virtual Command Line) API
│   └── webdav.ts          # WebDAV API
├── components/            # Reusable components
│   ├── Layout.tsx         # Main layout wrapper
│   ├── admin/             # Admin components
│   ├── benchmark/         # Benchmark components
│   ├── cloud/             # Cloud import components
│   ├── dashboard/         # Dashboard widgets
│   ├── fan-control/       # Fan control components
│   ├── file-manager/      # File manager components
│   ├── monitoring/        # Monitoring components
│   ├── plugins/           # Plugin components
│   ├── power/             # Power management components
│   ├── raid/              # RAID components
│   ├── rate-limits/       # Rate limit components
│   ├── samba/             # Samba components
│   ├── scheduler/         # Scheduler components
│   ├── services/          # Service status components
│   ├── system-monitor/    # System monitor components
│   ├── ui/                # Base UI components
│   ├── updates/           # Update components
│   ├── vcl/               # VCL components
│   └── webdav/            # WebDAV components
├── contexts/              # React contexts
│   └── ThemeContext.tsx   # Theme management
├── hooks/                 # Custom React hooks
│   ├── useActivityFeed.ts     # Activity feed hook
│   ├── useAdminDb.ts          # Admin DB hook
│   ├── useAsyncData.ts        # Generic async data hook
│   ├── useBenchmark.ts        # Benchmark hook
│   ├── useConfirmDialog.ts    # Confirm dialog hook
│   ├── useFanControl.ts       # Fan control hook
│   ├── useIdleTimeout.ts      # Idle timeout hook
│   ├── useLiveActivities.ts   # Live activities hook
│   ├── useMemoizedApi.ts      # Memoized API hook
│   ├── useMobile.ts           # Mobile devices hook
│   ├── useMonitoring.ts       # Monitoring hook
│   ├── useNetworkStatus.ts    # Network status hook
│   ├── useNextMaintenance.ts  # Next maintenance hook
│   ├── useNotificationSocket.ts # Notification WebSocket
│   ├── usePluginsSummary.ts   # Plugins summary hook
│   ├── usePowerMonitoring.ts  # Power monitoring hook
│   ├── useRemoteServers.ts    # Remote servers hook
│   ├── useSchedulers.ts       # Schedulers hook
│   ├── useServicesSummary.ts  # Services summary hook
│   ├── useSmartData.ts        # SMART data hook
│   └── useSystemTelemetry.ts  # System metrics hook
├── i18n/                  # Internationalization
├── lib/                   # Utility libraries
│   └── api.ts             # Base API client
├── pages/                 # Page components
│   ├── AdminDatabase.tsx      # Database admin tools
│   ├── AdminHealth.tsx        # System health dashboard
│   ├── ApiCenterPage.tsx      # API documentation center
│   ├── BackupPage.tsx         # Backup management
│   ├── CloudImportPage.tsx    # Cloud import
│   ├── Dashboard.tsx          # Main dashboard
│   ├── DeviceManagement.tsx   # Device management
│   ├── DevicesPage.tsx        # Devices overview
│   ├── FanControl.tsx         # Fan control
│   ├── FileManager.tsx        # File management
│   ├── Logging.tsx            # Audit logs
│   ├── Login.tsx              # Login page
│   ├── MobileDevicesPage.tsx  # Mobile devices
│   ├── NotificationPreferencesPage.tsx # Notification settings
│   ├── PluginsPage.tsx        # Plugin management
│   ├── PowerManagement.tsx    # Power management
│   ├── PublicSharePage.tsx    # Public share access
│   ├── RaidManagement.tsx     # RAID configuration
│   ├── RemoteServersPage.tsx  # Remote servers
│   ├── SchedulerDashboard.tsx # Scheduled tasks
│   ├── SettingsPage.tsx       # User settings
│   ├── SharesPage.tsx         # File shares
│   ├── SyncPrototype.tsx      # Sync management
│   ├── SystemControlPage.tsx  # System control
│   ├── SystemMonitor.tsx      # System monitoring
│   ├── UpdatePage.tsx         # System updates
│   ├── UserManagement.tsx     # User management (Admin)
│   └── VpnPage.tsx            # VPN management
├── App.tsx                # Main app component
└── main.tsx               # Entry point
```

## 🎨 Features

### Authentication & Security
- JWT token-based authentication
- Two-Factor Authentication (2FA/TOTP)
- Protected routes
- Role-based access control (Admin/User)
- Automatic token refresh
- Idle timeout handling

### Dashboard
- Real-time system metrics (CPU, RAM, Network)
- Live charts with Recharts
- Storage overview with quota visualization
- RAID status monitoring
- SMART disk health indicators
- Activity feed
- Next maintenance indicator
- Service status overview

### File Manager
- Drag & drop file upload
- Multi-file upload support
- Chunked upload for large files
- File preview (images, videos, PDFs, text)
- Folder navigation with breadcrumbs
- File operations (create, rename, move, delete)
- File sharing with public links
- Granular file permissions
- File versioning

### Backup & Sync
- Backup creation and management
- Incremental backup support
- Scheduled backups
- Backup restore functionality
- Desktop sync client integration
- Conflict resolution UI

### User Management (Admin)
- User CRUD operations
- Role assignment (Admin/User)
- User activity tracking
- Quota management
- Mobile device management

### RAID Management (Admin)
- RAID array status monitoring
- Disk health visualization
- Array creation wizard
- Degraded/rebuild simulation (Dev mode)
- SMART data integration
- SSD cache configuration

### Power & Energy
- CPU power management
- Power presets (Performance/Balanced/Powersave)
- Fan control with temperature monitoring
- Tapo smart plug integration
- Energy monitoring and cost calculation
- Power consumption history

### System & Monitoring
- Live telemetry charts
- Disk I/O monitoring
- Process list
- Network statistics
- Historical data visualization
- Service status management
- System control (shutdown/reboot)

### Scheduling
- Scheduler dashboard
- Scheduled backup tasks
- Cleanup automation
- Custom task scheduling

### Plugins & Extensions
- Plugin management interface
- Enable/disable plugins
- Plugin configuration

### Network Services
- VPN management (WireGuard)
- WebDAV server control
- Samba share management
- Remote server profiles

### Cloud Integration
- Cloud import (Dropbox, Google Drive, OneDrive)
- Import progress tracking

### Notifications
- Real-time WebSocket notifications
- Notification preferences
- Email notification settings

### Admin Tools
- Database health monitoring
- Benchmark tools
- Rate limiting configuration
- VCL (Virtual Command Line)
- API Center / Documentation
- System updates

### Settings
- User profile management
- Password change
- Two-factor authentication setup
- Theme selection
- Language settings
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
- Token refresh handling

### API Modules
Specialized API clients in `src/api/`:

**Storage & Files**
- `backup.ts` - Backup management
- `shares.ts` - File sharing
- `ssd-cache.ts` - SSD cache management
- `sync-schedules.ts` - Sync scheduling

**System & Hardware**
- `raid.ts` - RAID management
- `smart.ts` - SMART monitoring
- `system.ts` - System information
- `monitoring.ts` - System monitoring
- `fan-control.ts` - Fan control
- `benchmark.ts` - Storage benchmarks

**Power & Energy**
- `power.ts` - Power status
- `power-management.ts` - Power management
- `energy.ts` - Energy monitoring

**Network & Services**
- `webdav.ts` - WebDAV server
- `samba.ts` - Samba shares
- `service-status.ts` - Service status
- `remote-servers.ts` - Remote servers

**Users & Devices**
- `users.ts` - User management
- `devices.ts` - Device management
- `two-factor.ts` - 2FA/TOTP

**Automation & Extensions**
- `schedulers.ts` - Scheduled tasks
- `plugins.ts` - Plugin management
- `updates.ts` - System updates
- `notifications.ts` - Notifications
- `cloud-import.ts` - Cloud import

**Admin**
- `logging.ts` - Audit logs
- `vcl.ts` - Virtual Command Line

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

### Data Fetching Hooks

**useSystemTelemetry**
Real-time system metrics with auto-refresh:
```typescript
const { telemetry, loading, error } = useSystemTelemetry(5000); // 5s interval
```

**useSmartData**
SMART disk health monitoring:
```typescript
const { smartData, loading, error } = useSmartData();
```

**useAsyncData**
Generic async data fetching with loading/error states:
```typescript
const { data, loading, error, refetch } = useAsyncData(fetchFn);
```

### Feature-Specific Hooks

- **useActivityFeed** - Real-time activity feed
- **useAdminDb** - Admin database operations
- **useBenchmark** - Storage benchmark results
- **useFanControl** - Fan speed and mode control
- **useLiveActivities** - Live activity updates
- **useMobile** - Mobile device management
- **useMonitoring** - System monitoring data
- **usePluginsSummary** - Plugin status overview
- **usePowerMonitoring** - Power consumption data
- **useRemoteServers** - Remote server management
- **useSchedulers** - Scheduled task management
- **useServicesSummary** - Service status overview

### Utility Hooks

- **useConfirmDialog** - Confirmation dialog management
- **useIdleTimeout** - User idle detection
- **useMemoizedApi** - Memoized API calls
- **useNetworkStatus** - Network connectivity status
- **useNextMaintenance** - Next scheduled maintenance
- **useNotificationSocket** - WebSocket notifications

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
- **Technical Docs**: `../docs/TECHNICAL_DOCUMENTATION.md`
- **API Reference**: `../docs/api/API_REFERENCE.md`
- **User Guide**: `../docs/getting-started/USER_GUIDE.md`

## 🤝 Contributing

See `../CONTRIBUTING.md` for guidelines.

## 📄 License

See `../LICENSE` for details.

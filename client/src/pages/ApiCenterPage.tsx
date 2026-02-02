import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Code,
  Lock,
  FileText,
  Terminal,
  Activity,
  Shield,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Zap,
  Settings,
  BookOpen,
  RefreshCw,
  Users,
  Smartphone,
  Database,
  HardDrive,
  Wifi,
  Power,
  Cloud
} from 'lucide-react';
import toast from 'react-hot-toast';
import { buildApiUrl } from '../lib/api';
import { AdminBadge } from '../components/ui/AdminBadge';

// ==================== Types ====================

interface User {
  id: string;
  username: string;
  role: string;
}

interface ApiEndpoint {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  path: string;
  description: string;
  requiresAuth?: boolean;
  params?: { name: string; type: string; required: boolean; description: string }[];
  body?: { field: string; type: string; required: boolean; description: string }[];
  bodyExample?: string;
  response?: string;
  rateLimit?: string;
}

interface ApiSection {
  title: string;
  icon: React.ReactNode;
  endpoints: ApiEndpoint[];
}

interface RateLimitConfig {
  id: number;
  endpoint_type: string;
  limit_string: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
  updated_by: number | null;
}

// ==================== API Sections Data ====================

const getApiSections = (t: (key: string) => string): ApiSection[] => [
  {
    title: t('system:apiCenter.docs.authentication.title'),
    icon: <Lock className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/auth/login',
        description: t('system:apiCenter.docs.authentication.login'),
        rateLimit: 'auth_login',
        body: [
          { field: 'username', type: 'string', required: true, description: t('system:apiCenter.docs.params.username') },
          { field: 'password', type: 'string', required: true, description: t('system:apiCenter.docs.params.password') }
        ],
        bodyExample: `{
  "username": "admin",
  "password": "your_password"
}`,
        response: `{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": { "id": 1, "username": "admin", "role": "admin" }
}`
      },
      {
        method: 'POST',
        path: '/api/auth/register',
        description: t('system:apiCenter.docs.authentication.register'),
        rateLimit: 'auth_register',
        body: [
          { field: 'username', type: 'string', required: true, description: t('system:apiCenter.docs.params.username') },
          { field: 'email', type: 'string', required: true, description: t('system:apiCenter.docs.params.email') },
          { field: 'password', type: 'string', required: true, description: t('system:apiCenter.docs.params.password') }
        ],
        bodyExample: `{
  "username": "newuser",
  "email": "user@example.com",
  "password": "secure_password123"
}`,
        response: `{
  "id": 2,
  "username": "newuser",
  "email": "user@example.com",
  "role": "user"
}`
      },
      {
        method: 'GET',
        path: '/api/auth/me',
        description: t('system:apiCenter.docs.authentication.me'),
        requiresAuth: true,
        response: `{
  "user": { "id": 1, "username": "admin", "role": "admin" }
}`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.files.title'),
    icon: <FileText className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/files/list',
        description: t('system:apiCenter.docs.files.list'),
        requiresAuth: true,
        rateLimit: 'file_list',
        params: [
          { name: 'path', type: 'string', required: false, description: t('system:apiCenter.docs.params.directoryPath') }
        ],
        response: `{
  "files": [
    { "name": "doc.pdf", "size": 1048576, "is_directory": false }
  ]
}`
      },
      {
        method: 'POST',
        path: '/api/files/upload',
        description: t('system:apiCenter.docs.files.upload'),
        requiresAuth: true,
        rateLimit: 'file_upload',
        body: [
          { field: 'file', type: 'file', required: true, description: t('system:apiCenter.docs.params.fileToUpload') },
          { field: 'path', type: 'string', required: false, description: t('system:apiCenter.docs.params.targetDirectory') }
        ],
        bodyExample: `// FormData request:
// file: <binary file data>
// path: "/documents"`,
        response: `{ "filename": "uploaded.txt", "path": "/uploaded.txt", "size": 2048 }`
      },
      {
        method: 'GET',
        path: '/api/files/download/{path}',
        description: t('system:apiCenter.docs.files.download'),
        requiresAuth: true,
        rateLimit: 'file_download',
        params: [
          { name: 'path', type: 'string', required: true, description: t('system:apiCenter.docs.params.filePath') }
        ],
        response: t('system:apiCenter.docs.responses.binaryFileContent')
      },
      {
        method: 'DELETE',
        path: '/api/files/{path}',
        description: t('system:apiCenter.docs.files.delete'),
        requiresAuth: true,
        rateLimit: 'file_delete',
        params: [
          { name: 'path', type: 'string', required: true, description: t('system:apiCenter.docs.params.pathToDelete') }
        ],
        response: `{ "message": "Path deleted successfully" }`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.shares.title'),
    icon: <Shield className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/shares',
        description: t('system:apiCenter.docs.shares.list'),
        requiresAuth: true,
        rateLimit: 'share_list',
        response: `{
  "shares": [
    { "id": 1, "path": "/shared", "token": "abc123", "expires_at": null }
  ]
}`
      },
      {
        method: 'POST',
        path: '/api/shares',
        description: t('system:apiCenter.docs.shares.create'),
        requiresAuth: true,
        rateLimit: 'share_create',
        body: [
          { field: 'path', type: 'string', required: true, description: t('system:apiCenter.docs.params.pathToShare') },
          { field: 'expires_in_hours', type: 'number', required: false, description: t('system:apiCenter.docs.params.expirationHours') }
        ],
        bodyExample: `{
  "path": "/documents/report.pdf",
  "expires_in_hours": 24
}`,
        response: `{ "token": "abc123", "url": "/share/abc123" }`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.system.title'),
    icon: <Activity className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/system/info',
        description: t('system:apiCenter.docs.system.info'),
        requiresAuth: true,
        rateLimit: 'system_monitor',
        response: `{
  "hostname": "baluhost-nas",
  "os": "Linux",
  "cpu_count": 8,
  "total_memory": 17179869184
}`
      },
      {
        method: 'GET',
        path: '/api/system/telemetry',
        description: t('system:apiCenter.docs.system.telemetry'),
        requiresAuth: true,
        rateLimit: 'system_monitor',
        response: `{
  "cpu_usage": 25.5,
  "memory_used": 8589934592,
  "uptime": 86400
}`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.logging.title'),
    icon: <Terminal className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/logging/disk-io',
        description: t('system:apiCenter.docs.logging.diskIo'),
        requiresAuth: true,
        response: `{
  "logs": [{ "timestamp": "...", "operation": "read", "bytes": 4096 }]
}`
      },
      {
        method: 'GET',
        path: '/api/logging/file-access',
        description: t('system:apiCenter.docs.logging.fileAccess'),
        requiresAuth: true,
        response: `{
  "logs": [{ "timestamp": "...", "user": "admin", "action": "download" }]
}`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.users.title'),
    icon: <Users className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/users',
        description: t('system:apiCenter.docs.users.list'),
        requiresAuth: true,
        params: [
          { name: 'search', type: 'string', required: false, description: t('system:apiCenter.docs.params.searchByUsernameEmail') },
          { name: 'role', type: 'string', required: false, description: t('system:apiCenter.docs.params.filterByRole') },
          { name: 'is_active', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.filterByActiveStatus') }
        ],
        response: `{
  "users": [...],
  "total": 10,
  "active": 8,
  "inactive": 2,
  "admins": 2
}`
      },
      {
        method: 'POST',
        path: '/api/users',
        description: t('system:apiCenter.docs.users.create'),
        requiresAuth: true,
        rateLimit: 'user_create',
        body: [
          { field: 'username', type: 'string', required: true, description: t('system:apiCenter.docs.params.username') },
          { field: 'email', type: 'string', required: true, description: t('system:apiCenter.docs.params.email') },
          { field: 'password', type: 'string', required: true, description: t('system:apiCenter.docs.params.password') },
          { field: 'role', type: 'string', required: true, description: t('system:apiCenter.docs.params.filterByRole') }
        ],
        bodyExample: `{
  "username": "newuser",
  "email": "user@example.com",
  "password": "secure_password123",
  "role": "user"
}`,
        response: `{
  "id": 3,
  "username": "newuser",
  "email": "user@example.com",
  "role": "user"
}`
      },
      {
        method: 'PUT',
        path: '/api/users/{user_id}',
        description: t('system:apiCenter.docs.users.update'),
        requiresAuth: true,
        params: [
          { name: 'user_id', type: 'string', required: true, description: t('system:apiCenter.docs.params.userId') }
        ],
        body: [
          { field: 'email', type: 'string', required: false, description: t('system:apiCenter.docs.params.newEmail') },
          { field: 'role', type: 'string', required: false, description: t('system:apiCenter.docs.params.newRole') },
          { field: 'password', type: 'string', required: false, description: t('system:apiCenter.docs.params.newPassword') }
        ],
        bodyExample: `{
  "email": "newemail@example.com",
  "role": "admin"
}`
      },
      {
        method: 'DELETE',
        path: '/api/users/{user_id}',
        description: t('system:apiCenter.docs.users.delete'),
        requiresAuth: true,
        params: [
          { name: 'user_id', type: 'string', required: true, description: t('system:apiCenter.docs.params.userIdToDelete') }
        ]
      },
      {
        method: 'POST',
        path: '/api/users/{user_id}/avatar',
        description: t('system:apiCenter.docs.users.avatar'),
        requiresAuth: true,
        params: [
          { name: 'user_id', type: 'string', required: true, description: t('system:apiCenter.docs.params.userId') }
        ],
        body: [
          { field: 'avatar', type: 'file', required: true, description: t('system:apiCenter.docs.params.avatarImage') }
        ]
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.vpn.title'),
    icon: <Wifi className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/vpn/generate-config',
        description: t('system:apiCenter.docs.vpn.generateConfig'),
        requiresAuth: true,
        body: [
          { field: 'device_name', type: 'string', required: true, description: t('system:apiCenter.docs.params.deviceNameForVpn') },
          { field: 'server_public_endpoint', type: 'string', required: true, description: t('system:apiCenter.docs.params.serverEndpoint') }
        ],
        bodyExample: `{
  "device_name": "iPhone-Work",
  "server_public_endpoint": "vpn.example.com:51820"
}`,
        response: `{
  "config_file": "...",
  "qr_code_data": "..."
}`
      },
      {
        method: 'GET',
        path: '/api/vpn/clients',
        description: t('system:apiCenter.docs.vpn.listClients'),
        requiresAuth: true,
        response: `{
  "clients": [
    { "id": 1, "device_name": "iPhone", "is_active": true }
  ]
}`
      },
      {
        method: 'GET',
        path: '/api/vpn/clients/{client_id}',
        description: t('system:apiCenter.docs.vpn.getClient'),
        requiresAuth: true,
        params: [
          { name: 'client_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.clientId') }
        ]
      },
      {
        method: 'PATCH',
        path: '/api/vpn/clients/{client_id}',
        description: t('system:apiCenter.docs.vpn.updateClient'),
        requiresAuth: true,
        params: [
          { name: 'client_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.clientId') }
        ],
        body: [
          { field: 'device_name', type: 'string', required: false, description: t('system:apiCenter.docs.params.newDeviceName') },
          { field: 'is_active', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.activeStatus') }
        ],
        bodyExample: `{
  "device_name": "iPhone-Personal",
  "is_active": true
}`
      },
      {
        method: 'DELETE',
        path: '/api/vpn/clients/{client_id}',
        description: t('system:apiCenter.docs.vpn.deleteClient'),
        requiresAuth: true,
        params: [
          { name: 'client_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.clientId') }
        ]
      },
      {
        method: 'POST',
        path: '/api/vpn/fritzbox/upload',
        description: t('system:apiCenter.docs.vpn.fritzboxUpload'),
        requiresAuth: true,
        body: [
          { field: 'config_content', type: 'string', required: true, description: t('system:apiCenter.docs.params.wireguardConfig') },
          { field: 'public_endpoint', type: 'string', required: true, description: t('system:apiCenter.docs.params.fritzboxEndpoint') }
        ],
        bodyExample: `{
  "config_content": "[Interface]\\nPrivateKey = ...\\n...",
  "public_endpoint": "myfritz.dyndns.org:51820"
}`
      },
      {
        method: 'GET',
        path: '/api/vpn/fritzbox/qr',
        description: t('system:apiCenter.docs.vpn.fritzboxQr'),
        requiresAuth: true,
        response: `{ "config_base64": "..." }`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.mobile.title'),
    icon: <Smartphone className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/mobile/token/generate',
        description: t('system:apiCenter.docs.mobile.generateToken'),
        requiresAuth: true,
        params: [
          { name: 'include_vpn', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.includeVpn') },
          { name: 'device_name', type: 'string', required: false, description: t('system:apiCenter.docs.params.defaultIosDevice') },
          { name: 'token_validity_days', type: 'integer', required: false, description: t('system:apiCenter.docs.params.tokenValidity') }
        ],
        response: `{
  "token": "...",
  "qr_code_data": "...",
  "expires_at": "..."
}`
      },
      {
        method: 'POST',
        path: '/api/mobile/register',
        description: t('system:apiCenter.docs.mobile.register'),
        body: [
          { field: 'registration_token', type: 'string', required: true, description: t('system:apiCenter.docs.params.tokenFromQr') },
          { field: 'device_name', type: 'string', required: true, description: t('system:apiCenter.docs.params.deviceName') },
          { field: 'platform', type: 'string', required: true, description: t('system:apiCenter.docs.params.platform') }
        ],
        bodyExample: `{
  "registration_token": "abc123xyz...",
  "device_name": "iPhone 15 Pro",
  "platform": "ios"
}`,
        response: `{
  "access_token": "...",
  "device_id": "...",
  "user": {...}
}`
      },
      {
        method: 'GET',
        path: '/api/mobile/devices',
        description: t('system:apiCenter.docs.mobile.listDevices'),
        requiresAuth: true,
        response: `{
  "devices": [
    { "id": "...", "device_name": "iPhone", "platform": "ios", "is_active": true }
  ]
}`
      },
      {
        method: 'DELETE',
        path: '/api/mobile/devices/{device_id}',
        description: t('system:apiCenter.docs.mobile.deleteDevice'),
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'string', required: true, description: t('system:apiCenter.docs.params.deviceId') }
        ]
      },
      {
        method: 'POST',
        path: '/api/mobile/devices/{device_id}/push-token',
        description: t('system:apiCenter.docs.mobile.pushToken'),
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'string', required: true, description: t('system:apiCenter.docs.params.deviceId') }
        ],
        body: [
          { field: 'push_token', type: 'string', required: true, description: t('system:apiCenter.docs.params.fcmToken') }
        ],
        bodyExample: `{
  "push_token": "fcm_token_string..."
}`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.backup.title'),
    icon: <Database className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/backup',
        description: t('system:apiCenter.docs.backup.create'),
        requiresAuth: true,
        body: [
          { field: 'includes_database', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.includeDatabase') },
          { field: 'includes_files', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.includeFiles') },
          { field: 'includes_config', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.includeConfig') },
          { field: 'description', type: 'string', required: false, description: t('system:apiCenter.docs.params.backupDescription') }
        ],
        bodyExample: `{
  "includes_database": true,
  "includes_files": true,
  "includes_config": true,
  "description": "Weekly backup"
}`,
        response: `{
  "id": 1,
  "filename": "backup_2025-01-25.tar.gz",
  "size_bytes": 1048576,
  "created_at": "..."
}`
      },
      {
        method: 'GET',
        path: '/api/backup',
        description: t('system:apiCenter.docs.backup.list'),
        requiresAuth: true,
        response: `{
  "backups": [...],
  "total_size_bytes": 5242880,
  "total_size_mb": 5.0
}`
      },
      {
        method: 'GET',
        path: '/api/backup/{backup_id}',
        description: t('system:apiCenter.docs.backup.get'),
        requiresAuth: true,
        params: [
          { name: 'backup_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.backupId') }
        ]
      },
      {
        method: 'DELETE',
        path: '/api/backup/{backup_id}',
        description: t('system:apiCenter.docs.backup.delete'),
        requiresAuth: true,
        params: [
          { name: 'backup_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.backupId') }
        ]
      },
      {
        method: 'POST',
        path: '/api/backup/{backup_id}/restore',
        description: t('system:apiCenter.docs.backup.restore'),
        requiresAuth: true,
        params: [
          { name: 'backup_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.backupId') }
        ],
        body: [
          { field: 'confirm', type: 'boolean', required: true, description: t('system:apiCenter.docs.params.confirmTrue') },
          { field: 'restore_database', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.restoreDatabase') },
          { field: 'restore_files', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.restoreFiles') },
          { field: 'restore_config', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.restoreConfig') }
        ],
        bodyExample: `{
  "confirm": true,
  "restore_database": true,
  "restore_files": true,
  "restore_config": false
}`
      },
      {
        method: 'GET',
        path: '/api/backup/{backup_id}/download',
        description: t('system:apiCenter.docs.backup.download'),
        requiresAuth: true,
        params: [
          { name: 'backup_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.backupId') }
        ],
        response: t('system:apiCenter.docs.responses.binaryBackupFile')
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.power.title'),
    icon: <Power className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/power/status',
        description: t('system:apiCenter.docs.power.status'),
        requiresAuth: true,
        response: `{
  "current_profile": "balanced",
  "cpu_frequency_mhz": 2400,
  "active_demands": [],
  "auto_scaling_enabled": true
}`
      },
      {
        method: 'GET',
        path: '/api/power/profiles',
        description: t('system:apiCenter.docs.power.profiles'),
        requiresAuth: true,
        response: `{
  "profiles": [
    { "name": "power-save", "governor": "powersave", "epp": "power" },
    { "name": "balanced", "governor": "schedutil", "epp": "balance_performance" },
    { "name": "performance", "governor": "performance", "epp": "performance" }
  ],
  "current_profile": "balanced"
}`
      },
      {
        method: 'POST',
        path: '/api/power/profile',
        description: t('system:apiCenter.docs.power.setProfile'),
        requiresAuth: true,
        body: [
          { field: 'profile', type: 'string', required: true, description: t('system:apiCenter.docs.params.profileName') },
          { field: 'reason', type: 'string', required: false, description: t('system:apiCenter.docs.params.reasonForChange') },
          { field: 'duration_seconds', type: 'integer', required: false, description: t('system:apiCenter.docs.params.overrideDuration') }
        ],
        bodyExample: `{
  "profile": "performance",
  "reason": "Heavy workload",
  "duration_seconds": 3600
}`
      },
      {
        method: 'POST',
        path: '/api/power/demand/register',
        description: t('system:apiCenter.docs.power.registerDemand'),
        requiresAuth: true,
        body: [
          { field: 'source', type: 'string', required: true, description: t('system:apiCenter.docs.params.demandSource') },
          { field: 'priority', type: 'integer', required: true, description: t('system:apiCenter.docs.params.priority') },
          { field: 'description', type: 'string', required: false, description: t('system:apiCenter.docs.params.demandDescription') }
        ],
        bodyExample: `{
  "source": "video_transcode",
  "priority": 8,
  "description": "Video transcoding job"
}`
      },
      {
        method: 'POST',
        path: '/api/power/demand/unregister',
        description: t('system:apiCenter.docs.power.unregisterDemand'),
        requiresAuth: true,
        body: [
          { field: 'source', type: 'string', required: true, description: t('system:apiCenter.docs.params.demandSource') }
        ],
        bodyExample: `{
  "source": "video_transcode"
}`
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.tapo.title'),
    icon: <Cloud className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/tapo/devices',
        description: t('system:apiCenter.docs.tapo.add'),
        requiresAuth: true,
        body: [
          { field: 'name', type: 'string', required: true, description: t('system:apiCenter.docs.params.tapoDeviceName') },
          { field: 'device_type', type: 'string', required: true, description: t('system:apiCenter.docs.params.tapoDeviceType') },
          { field: 'ip_address', type: 'string', required: true, description: t('system:apiCenter.docs.params.tapoIpAddress') },
          { field: 'email', type: 'string', required: true, description: t('system:apiCenter.docs.params.tapoEmail') },
          { field: 'password', type: 'string', required: true, description: t('system:apiCenter.docs.params.tapoPassword') },
          { field: 'is_monitoring', type: 'boolean', required: false, description: t('system:apiCenter.docs.params.enableMonitoring') }
        ],
        bodyExample: `{
  "name": "Server Power",
  "device_type": "P115",
  "ip_address": "192.168.1.50",
  "email": "user@example.com",
  "password": "tapo_password",
  "is_monitoring": true
}`
      },
      {
        method: 'GET',
        path: '/api/tapo/devices',
        description: t('system:apiCenter.docs.tapo.list'),
        requiresAuth: true,
        response: `{
  "devices": [
    { "id": 1, "name": "Server Power", "device_type": "P115", "is_active": true }
  ]
}`
      },
      {
        method: 'GET',
        path: '/api/tapo/devices/{device_id}/current-power',
        description: t('system:apiCenter.docs.tapo.currentPower'),
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.tapoDeviceId') }
        ],
        response: `{
  "current_power_w": 45.2,
  "voltage_v": 230.1,
  "current_a": 0.196,
  "timestamp": "..."
}`
      },
      {
        method: 'DELETE',
        path: '/api/tapo/devices/{device_id}',
        description: t('system:apiCenter.docs.tapo.remove'),
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'integer', required: true, description: t('system:apiCenter.docs.params.tapoDeviceId') }
        ]
      }
    ]
  },
  {
    title: t('system:apiCenter.docs.raid.title'),
    icon: <HardDrive className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/system/raid/status',
        description: t('system:apiCenter.docs.raid.status'),
        requiresAuth: true,
        response: `{
  "arrays": [
    { "name": "md0", "level": "raid1", "state": "active", "devices": [...] }
  ]
}`
      },
      {
        method: 'POST',
        path: '/api/system/raid/create',
        description: t('system:apiCenter.docs.raid.create'),
        requiresAuth: true,
        body: [
          { field: 'name', type: 'string', required: true, description: t('system:apiCenter.docs.params.arrayName') },
          { field: 'level', type: 'string', required: true, description: t('system:apiCenter.docs.params.raidLevel') },
          { field: 'devices', type: 'array', required: true, description: t('system:apiCenter.docs.params.devicePaths') }
        ],
        bodyExample: `{
  "name": "md0",
  "level": "1",
  "devices": ["/dev/sda", "/dev/sdb"]
}`
      },
      {
        method: 'DELETE',
        path: '/api/system/raid/{array_name}',
        description: t('system:apiCenter.docs.raid.delete'),
        requiresAuth: true,
        params: [
          { name: 'array_name', type: 'string', required: true, description: t('system:apiCenter.docs.params.arrayNameParam') }
        ]
      },
      {
        method: 'GET',
        path: '/api/system/smart',
        description: t('system:apiCenter.docs.raid.smart'),
        requiresAuth: true,
        response: `{
  "disks": [
    { "device": "/dev/sda", "model": "...", "health": "PASSED", "temp": 35 }
  ]
}`
      },
      {
        method: 'GET',
        path: '/api/system/available-disks',
        description: t('system:apiCenter.docs.raid.availableDisks'),
        requiresAuth: true,
        response: `{
  "disks": [
    { "path": "/dev/sda", "size_gb": 500, "model": "..." }
  ]
}`
      }
    ]
  }
];

// ==================== Method Colors ====================

const methodColors: Record<string, string> = {
  GET: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  POST: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  PUT: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  DELETE: 'bg-red-500/20 text-red-400 border-red-500/30'
};

// ==================== Endpoint Card Component ====================

interface EndpointCardProps {
  endpoint: ApiEndpoint;
  rateLimits: Record<string, RateLimitConfig>;
  isAdmin: boolean;
  t: (key: string) => string;
  onEditRateLimit?: (config: RateLimitConfig) => void;
}

function EndpointCard({ endpoint, rateLimits, isAdmin, t, onEditRateLimit }: EndpointCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const rateLimit = endpoint.rateLimit ? rateLimits[endpoint.rateLimit] : null;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-3 sm:p-4 hover:border-slate-600/50 transition-all">
      <div
        className="flex items-center justify-between cursor-pointer touch-manipulation"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2 sm:gap-3 flex-1 flex-wrap min-w-0">
          <span className={`px-2 sm:px-3 py-1 rounded-lg text-[10px] sm:text-xs font-bold border flex-shrink-0 ${methodColors[endpoint.method]}`}>
            {endpoint.method}
          </span>
          <code className="text-cyan-400 font-mono text-xs sm:text-sm truncate">{endpoint.path}</code>
          <span className="text-slate-400 text-xs sm:text-sm hidden lg:inline truncate">{endpoint.description}</span>
          {endpoint.requiresAuth && (
            <span title={t('system:apiCenter.authRequired')} className="flex-shrink-0"><Shield className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-amber-400" /></span>
          )}
          {rateLimit && (
            <span
              className={`px-1.5 sm:px-2 py-0.5 rounded text-[10px] sm:text-xs font-mono flex-shrink-0 ${
                rateLimit.enabled
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-slate-500/20 text-slate-500'
              }`}
              title={`Rate limit: ${rateLimit.limit_string}`}
            >
              <Zap className="w-2.5 h-2.5 sm:w-3 sm:h-3 inline mr-0.5 sm:mr-1" />
              <span className="hidden sm:inline">{rateLimit.limit_string}</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0 ml-2">
          {isAdmin && rateLimit && onEditRateLimit && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEditRateLimit(rateLimit);
              }}
              className="p-2 sm:p-1.5 rounded-lg bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors touch-manipulation active:scale-95 min-w-[36px] min-h-[36px] sm:min-w-0 sm:min-h-0 flex items-center justify-center"
              title={t('system:apiCenter.buttons.editRateLimit')}
            >
              <Settings className="w-4 h-4" />
            </button>
          )}
          {isOpen ? (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </div>

      {isOpen && (
        <div className="mt-3 sm:mt-4 space-y-3 sm:space-y-4 border-t border-slate-700/50 pt-3 sm:pt-4">
          <p className="text-slate-300 text-xs sm:text-sm lg:hidden">{endpoint.description}</p>

          {endpoint.params && endpoint.params.length > 0 && (
            <div>
              <h4 className="text-xs sm:text-sm font-semibold text-slate-300 mb-2">{t('system:apiCenter.parameters')}</h4>
              <div className="space-y-1.5 sm:space-y-2">
                {endpoint.params.map((param, idx) => (
                  <div key={idx} className="flex items-start gap-2 sm:gap-3 text-xs sm:text-sm flex-wrap">
                    <code className="text-cyan-400 font-mono">{param.name}</code>
                    <span className="text-slate-500">({param.type})</span>
                    {param.required && <span className="text-red-400 text-[10px] sm:text-xs">{t('system:apiCenter.required')}</span>}
                    <span className="text-slate-400 w-full sm:w-auto">{param.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.body && endpoint.body.length > 0 && (
            <div>
              <h4 className="text-xs sm:text-sm font-semibold text-slate-300 mb-2">{t('system:apiCenter.requestBody')}</h4>
              <div className="space-y-1.5 sm:space-y-2">
                {endpoint.body.map((field, idx) => (
                  <div key={idx} className="flex items-start gap-2 sm:gap-3 text-xs sm:text-sm flex-wrap">
                    <code className="text-violet-400 font-mono">{field.field}</code>
                    <span className="text-slate-500">({field.type})</span>
                    {field.required && <span className="text-red-400 text-[10px] sm:text-xs">{t('system:apiCenter.required')}</span>}
                    <span className="text-slate-400 w-full sm:w-auto">{field.description}</span>
                  </div>
                ))}
              </div>
              {endpoint.bodyExample && (
                <div className="mt-3">
                  <div className="flex items-center justify-between mb-2">
                    <h5 className="text-xs font-semibold text-slate-400">{t('system:apiCenter.example')}</h5>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        copyToClipboard(endpoint.bodyExample!);
                      }}
                      className="text-slate-400 hover:text-cyan-400 transition-colors p-1 touch-manipulation active:scale-95"
                    >
                      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    </button>
                  </div>
                  <pre className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-2 sm:p-3 text-[10px] sm:text-xs overflow-x-auto">
                    <code className="text-violet-300">{endpoint.bodyExample}</code>
                  </pre>
                </div>
              )}
            </div>
          )}

          {endpoint.response && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs sm:text-sm font-semibold text-slate-300">{t('system:apiCenter.response')}</h4>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(endpoint.response!);
                  }}
                  className="text-slate-400 hover:text-cyan-400 transition-colors p-2 -mr-2 touch-manipulation active:scale-95 min-w-[36px] min-h-[36px] flex items-center justify-center"
                >
                  {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              <pre className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-2 sm:p-3 text-[10px] sm:text-xs overflow-x-auto">
                <code className="text-slate-300">{endpoint.response}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ==================== Rate Limit Edit Modal ====================

interface RateLimitModalProps {
  config: RateLimitConfig | null;
  onClose: () => void;
  onSave: (endpointType: string, data: { limit_string: string; description: string; enabled: boolean }) => Promise<void>;
  t: (key: string) => string;
}

function RateLimitModal({ config, onClose, onSave, t }: RateLimitModalProps) {
  const [form, setForm] = useState({
    limit_string: config?.limit_string || '',
    description: config?.description || '',
    enabled: config?.enabled ?? true
  });
  const [saving, setSaving] = useState(false);

  if (!config) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(config.endpoint_type, form);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700/50 rounded-xl p-4 sm:p-6 w-full max-w-md max-h-[100vh] sm:max-h-[90vh] overflow-y-auto shadow-2xl">
        <h3 className="text-lg sm:text-xl font-bold text-white mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5 text-yellow-400" />
          {t('system:apiCenter.modal.editRateLimit')}
        </h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-xs sm:text-sm font-medium text-slate-300 mb-1">{t('system:apiCenter.modal.endpoint')}</label>
            <code className="block w-full px-3 py-2 bg-slate-900/60 border border-slate-700/50 rounded-lg text-cyan-400 text-xs sm:text-sm truncate">
              {config.endpoint_type}
            </code>
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-slate-300 mb-1">{t('system:apiCenter.modal.rateLimit')}</label>
            <input
              type="text"
              value={form.limit_string}
              onChange={(e) => setForm({ ...form, limit_string: e.target.value })}
              className="w-full px-3 py-2.5 bg-slate-900/60 border border-slate-700/50 rounded-lg text-white focus:border-cyan-500 focus:outline-none text-sm min-h-[44px]"
              placeholder="5/minute"
            />
            <p className="text-[10px] sm:text-xs text-slate-500 mt-1">{t('system:apiCenter.modal.rateLimitFormat')}</p>
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-slate-300 mb-1">{t('system:apiCenter.modal.description')}</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2.5 bg-slate-900/60 border border-slate-700/50 rounded-lg text-white focus:border-cyan-500 focus:outline-none text-sm min-h-[44px]"
              placeholder={t('system:apiCenter.modal.descriptionPlaceholder')}
            />
          </div>

          <div className="flex items-center gap-3 min-h-[44px]">
            <input
              type="checkbox"
              id="enabled"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="w-5 h-5 rounded"
            />
            <label htmlFor="enabled" className="text-sm text-slate-300">{t('system:apiCenter.modal.enabled')}</label>
          </div>
        </div>

        <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors touch-manipulation active:scale-95 min-h-[44px]"
          >
            {t('system:apiCenter.modal.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors disabled:opacity-50 touch-manipulation active:scale-95 min-h-[44px]"
          >
            {saving ? t('system:apiCenter.modal.saving') : t('system:apiCenter.modal.saveChanges')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export default function ApiCenterPage() {
  const { t } = useTranslation(['system', 'common']);
  const [user, setUser] = useState<User | null>(null);
  const [activeTab, setActiveTab] = useState<'docs' | 'limits'>('docs');
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [rateLimits, setRateLimits] = useState<Record<string, RateLimitConfig>>({});
  const [rateLimitsList, setRateLimitsList] = useState<RateLimitConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<RateLimitConfig | null>(null);

  const isAdmin = user?.role === 'admin';

  // Memoize API sections with translations
  const apiSections = useMemo(() => getApiSections(t), [t]);

  // Dynamically determine API base URL based on current location
  const getApiBaseUrl = (): string => {
    const hostname = window.location.hostname;
    const isDev = import.meta.env.DEV;

    // In development, backend runs on port 3001
    // In production, backend typically runs on port 8000
    const port = isDev ? 3001 : 8000;
    const protocol = window.location.protocol; // http: or https:

    return `${protocol}//${hostname}:${port}`;
  };

  const apiBaseUrl = getApiBaseUrl();

  // Load current user
  useEffect(() => {
    const fetchUser = async () => {
      const token = localStorage.getItem('token');
      if (!token) return;

      try {
        const response = await fetch(buildApiUrl('/api/auth/me'), {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          setUser(data.user || data);
        }
      } catch (error) {
        console.error('Failed to fetch user:', error);
      }
    };
    fetchUser();
  }, []);

  useEffect(() => {
    if (isAdmin) {
      loadRateLimits();
    } else {
      setLoading(false);
    }
  }, [isAdmin]);

  const loadRateLimits = async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits'), {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setRateLimitsList(data.configs);
        const map: Record<string, RateLimitConfig> = {};
        data.configs.forEach((c: RateLimitConfig) => {
          map[c.endpoint_type] = c;
        });
        setRateLimits(map);
      }
    } catch (error) {
      console.error('Failed to load rate limits:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveRateLimit = async (
    endpointType: string, 
    data: { limit_string: string; description: string; enabled: boolean }
  ) => {
    const token = localStorage.getItem('token');
    if (!token) {
      toast.error(t('system:apiCenter.toasts.notAuthenticated'));
      return;
    }

    const response = await fetch(buildApiUrl(`/api/admin/rate-limits/${endpointType}`), {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        limit_string: data.limit_string,
        description: data.description || null,
        enabled: data.enabled
      })
    });

    if (response.ok) {
      toast.success(t('system:apiCenter.toasts.rateLimitUpdated'));
      loadRateLimits();
    } else {
      const error = await response.json();
      toast.error(error.detail || t('system:apiCenter.toasts.updateFailed'));
      throw new Error('Failed to save');
    }
  };

  const handleSeedDefaults = async () => {
    if (!confirm(t('system:apiCenter.rateLimits.seedConfirm'))) return;

    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits/seed-defaults'), {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        toast.success(t('system:apiCenter.toasts.defaultsSeeded'));
        loadRateLimits();
      } else {
        toast.error(t('system:apiCenter.toasts.seedFailed'));
      }
    } catch (error) {
      toast.error(t('system:apiCenter.toasts.seedFailed'));
    }
  };

  const handleToggleEnabled = async (config: RateLimitConfig) => {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl(`/api/admin/rate-limits/${config.endpoint_type}`), {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled: !config.enabled })
      });

      if (response.ok) {
        toast.success(!config.enabled ? t('system:apiCenter.rateLimits.enabled') : t('system:apiCenter.rateLimits.disabled'));
        loadRateLimits();
      }
    } catch (error) {
      toast.error(t('system:apiCenter.toasts.updateFailed'));
    }
  };

  const filteredSections = selectedSection
    ? apiSections.filter(s => s.title === selectedSection)
    : apiSections;

  const getCategoryFromEndpoint = (endpoint: string): string => {
    if (endpoint.startsWith('auth_')) return t('system:apiCenter.categories.authentication');
    if (endpoint.startsWith('file_')) return t('system:apiCenter.categories.fileOperations');
    if (endpoint.startsWith('share_')) return t('system:apiCenter.categories.sharing');
    if (endpoint.startsWith('mobile_')) return t('system:apiCenter.categories.mobile');
    if (endpoint.startsWith('vpn_')) return t('system:apiCenter.categories.vpn');
    if (endpoint.includes('admin')) return t('system:apiCenter.categories.admin');
    if (endpoint.includes('user')) return t('system:apiCenter.categories.users');
    if (endpoint.includes('system')) return t('system:apiCenter.categories.system');
    return t('system:apiCenter.categories.other');
  };

  const groupedRateLimits = rateLimitsList.reduce((acc, config) => {
    const category = getCategoryFromEndpoint(config.endpoint_type);
    if (!acc[category]) acc[category] = [];
    acc[category].push(config);
    return acc;
  }, {} as Record<string, RateLimitConfig[]>);

  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent flex items-center gap-2 sm:gap-3">
            <Code className="w-6 h-6 sm:w-8 sm:h-8 text-cyan-400" />
            {t('system:apiCenter.title')}
          </h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-1">
            {t('system:apiCenter.subtitle')} <span className="hidden sm:inline">{t('system:apiCenter.tabs.documentation')}</span> {isAdmin && <span className="hidden sm:inline">& {t('system:apiCenter.tabs.rateLimits')}</span>}
          </p>
        </div>

        {/* Tab Buttons */}
        {isAdmin && (
          <div className="flex gap-1 sm:gap-2 bg-slate-800/40 p-1 rounded-lg">
            <button
              onClick={() => setActiveTab('docs')}
              className={`px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center gap-1.5 sm:gap-2 touch-manipulation active:scale-95 min-h-[40px] ${
                activeTab === 'docs'
                  ? 'bg-cyan-600 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              <span className="hidden sm:inline">API </span>{t('system:apiCenter.tabs.documentation')}
            </button>
            <button
              onClick={() => setActiveTab('limits')}
              className={`px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center gap-1.5 sm:gap-2 touch-manipulation active:scale-95 min-h-[40px] ${
                activeTab === 'limits'
                  ? 'bg-yellow-600 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Zap className="w-4 h-4" />
              <span className="hidden sm:inline">Rate </span>{t('system:apiCenter.tabs.rateLimits')}
              <AdminBadge />
            </button>
          </div>
        )}
      </div>

      {/* API Docs Tab */}
      {activeTab === 'docs' && (
        <>
          {/* Base URL Info */}
          <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-xl p-3 sm:p-4">
            <div className="flex items-start gap-2 sm:gap-3">
              <Code className="w-4 h-4 sm:w-5 sm:h-5 text-cyan-400 mt-0.5 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-white text-sm sm:text-base mb-1">{t('system:apiCenter.baseUrl')}</h3>
                <div className="flex items-center gap-2">
                  <code className="text-xs sm:text-sm text-cyan-400 bg-slate-900/60 px-2 sm:px-3 py-1 rounded block overflow-x-auto flex-1">
                    {apiBaseUrl}
                  </code>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(apiBaseUrl);
                      toast.success(t('system:apiCenter.baseUrlCopied'));
                    }}
                    className="p-2 bg-slate-700/50 hover:bg-slate-700 rounded-lg transition-colors flex-shrink-0 touch-manipulation active:scale-95"
                    title={t('system:apiCenter.baseUrl')}
                  >
                    <Copy className="w-4 h-4 text-slate-300" />
                  </button>
                </div>
                <p className="text-xs sm:text-sm text-slate-400 mt-2">
                  <span className="hidden sm:inline">{t('system:apiCenter.authRequiredNote')} </span>
                  <code className="text-[10px] sm:text-xs text-slate-300 bg-slate-900/60 px-1.5 sm:px-2 py-0.5 rounded sm:ml-2 block sm:inline mt-1 sm:mt-0 overflow-x-auto">
                    Authorization: Bearer {"<token>"}
                  </code>
                </p>
              </div>
            </div>
          </div>

          {/* Section Filter */}
          <div className="flex gap-1.5 sm:gap-2 flex-wrap overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 pb-2 sm:pb-0">
            <button
              onClick={() => setSelectedSection(null)}
              className={`px-2.5 sm:px-3 py-1.5 sm:py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 min-h-[36px] sm:min-h-0 whitespace-nowrap ${
                !selectedSection
                  ? 'bg-cyan-600 text-white'
                  : 'bg-slate-800/40 text-slate-400 hover:bg-slate-700/50 hover:text-white'
              }`}
            >
              {t('system:apiCenter.all')}
            </button>
            {apiSections.map((section) => (
              <button
                key={section.title}
                onClick={() => setSelectedSection(section.title)}
                className={`px-2.5 sm:px-3 py-1.5 sm:py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center gap-1.5 sm:gap-2 touch-manipulation active:scale-95 min-h-[36px] sm:min-h-0 whitespace-nowrap ${
                  selectedSection === section.title
                    ? 'bg-cyan-600 text-white'
                    : 'bg-slate-800/40 text-slate-400 hover:bg-slate-700/50 hover:text-white'
                }`}
              >
                {section.icon}
                <span className="hidden sm:inline">{section.title}</span>
              </button>
            ))}
          </div>

          {/* API Sections */}
          {filteredSections.map((section) => (
            <div key={section.title}>
              <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
                <div className="p-1.5 sm:p-2 bg-cyan-500/20 rounded-lg text-cyan-400">
                  {section.icon}
                </div>
                <h2 className="text-lg sm:text-xl font-bold text-white">{section.title}</h2>
              </div>
              <div className="space-y-2 sm:space-y-3">
                {section.endpoints.map((endpoint, idx) => (
                  <EndpointCard
                    key={idx}
                    endpoint={endpoint}
                    rateLimits={rateLimits}
                    isAdmin={isAdmin}
                    t={t}
                    onEditRateLimit={undefined}
                  />
                ))}
              </div>
            </div>
          ))}
        </>
      )}

      {/* Rate Limits Tab (Admin Only) */}
      {activeTab === 'limits' && isAdmin && (
        <>
          {/* Actions */}
          <div className="flex flex-wrap gap-2 sm:gap-3">
            <button
              onClick={handleSeedDefaults}
              className="px-3 sm:px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors flex items-center gap-2 text-xs sm:text-sm touch-manipulation active:scale-95 min-h-[40px]"
            >
              🌱 <span className="hidden sm:inline">{t('system:apiCenter.rateLimits.seedDefaults')}</span>
            </button>
            <button
              onClick={loadRateLimits}
              className="px-3 sm:px-4 py-2 bg-slate-700/50 hover:bg-slate-700 text-white rounded-lg transition-colors flex items-center gap-2 text-xs sm:text-sm touch-manipulation active:scale-95 min-h-[40px]"
            >
              <RefreshCw className="w-4 h-4" />
              <span className="hidden sm:inline">{t('system:apiCenter.buttons.refresh')}</span>
            </button>
          </div>

          {/* Info Box */}
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3 sm:p-4">
            <h3 className="text-yellow-400 font-semibold text-sm sm:text-base mb-2 flex items-center gap-2">
              <Zap className="w-4 h-4 sm:w-5 sm:h-5" />
              {t('system:apiCenter.rateLimits.title')}
            </h3>
            <p className="text-slate-300 text-xs sm:text-sm">
              <span className="hidden sm:inline">{t('system:apiCenter.rateLimits.description')} </span>{t('system:apiCenter.rateLimits.format')}: <code className="bg-slate-900/60 px-1.5 sm:px-2 py-0.5 rounded text-[10px] sm:text-xs">number/unit</code>
              {' '}({t('system:apiCenter.rateLimits.example')}, <code className="bg-slate-900/60 px-1.5 sm:px-2 py-0.5 rounded text-[10px] sm:text-xs">5/min</code>)
            </p>
          </div>

          {/* Rate Limits by Category */}
          {loading ? (
            <div className="text-slate-400 text-sm">{t('system:apiCenter.rateLimits.loading')}</div>
          ) : Object.keys(groupedRateLimits).length === 0 ? (
            <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-8 sm:p-12 text-center">
              <p className="text-slate-400 text-sm mb-4">{t('system:apiCenter.rateLimits.noConfigs')}</p>
              <button
                onClick={handleSeedDefaults}
                className="px-4 sm:px-6 py-2.5 sm:py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors text-sm touch-manipulation active:scale-95 min-h-[44px]"
              >
                🌱 {t('system:apiCenter.rateLimits.seedDefaults')}
              </button>
            </div>
          ) : (
            Object.entries(groupedRateLimits).map(([category, configs]) => (
              <div key={category} className="bg-slate-800/40 backdrop-blur-sm rounded-xl border-2 border-amber-500/40 overflow-hidden">
                {/* Category Header */}
                <div className="flex items-center gap-2 sm:gap-3 p-3 sm:p-4 border-b border-amber-500/30 bg-slate-800/60">
                  <div className="p-1.5 bg-amber-500/20 rounded-lg text-amber-400">
                    <Zap className="w-4 h-4" />
                  </div>
                  <h2 className="text-base sm:text-lg font-bold text-white">{category}</h2>
                  <span className="text-xs text-slate-500">({configs.length})</span>
                </div>

                {/* Table */}
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-xs text-slate-400 border-b border-slate-700/30">
                        <th className="px-3 sm:px-4 py-2 font-medium">{t('system:apiCenter.rateLimits.endpoint')}</th>
                        <th className="px-3 sm:px-4 py-2 font-medium">{t('system:apiCenter.rateLimits.limit')}</th>
                        <th className="px-3 sm:px-4 py-2 font-medium">{t('system:apiCenter.rateLimits.status')}</th>
                        <th className="px-3 sm:px-4 py-2 font-medium text-right">{t('system:apiCenter.rateLimits.actions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {configs.map((config) => (
                        <tr
                          key={config.id}
                          className="border-b border-slate-700/20 last:border-b-0 hover:bg-slate-700/20 transition-colors"
                          title={config.description || undefined}
                        >
                          <td className="px-3 sm:px-4 py-2.5 sm:py-3">
                            <code className="text-cyan-400 font-mono text-xs sm:text-sm">{config.endpoint_type}</code>
                          </td>
                          <td className="px-3 sm:px-4 py-2.5 sm:py-3">
                            <span className="text-emerald-400 font-semibold text-xs sm:text-sm font-mono">{config.limit_string}</span>
                          </td>
                          <td className="px-3 sm:px-4 py-2.5 sm:py-3">
                            <button
                              onClick={() => handleToggleEnabled(config)}
                              className={`px-2 py-1 rounded text-[10px] sm:text-xs font-medium transition-colors touch-manipulation active:scale-95 ${
                                config.enabled
                                  ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                                  : 'bg-slate-600/30 text-slate-400 hover:bg-slate-600/50'
                              }`}
                            >
                              {config.enabled ? `✓ ${t('system:apiCenter.rateLimits.active')}` : `✗ ${t('system:apiCenter.rateLimits.off')}`}
                            </button>
                          </td>
                          <td className="px-3 sm:px-4 py-2.5 sm:py-3 text-right">
                            <button
                              onClick={() => setEditingConfig(config)}
                              className="p-1.5 sm:p-2 bg-blue-600/20 hover:bg-blue-600/40 text-blue-400 rounded-lg transition-colors touch-manipulation active:scale-95"
                              title={t('system:apiCenter.buttons.editRateLimit')}
                            >
                              <Settings className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))
          )}
        </>
      )}

      {/* Edit Modal */}
      {editingConfig && (
        <RateLimitModal
          config={editingConfig}
          onClose={() => setEditingConfig(null)}
          onSave={handleSaveRateLimit}
          t={t}
        />
      )}
    </div>
  );
}

import { useState, useEffect } from 'react';
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
  Users,
  Share2,
  Smartphone,
  Wifi,
  Zap,
  Database
} from 'lucide-react';

interface ApiEndpoint {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  path: string;
  description: string;
  requiresAuth?: boolean;
  params?: { name: string; type: string; required: boolean; description: string }[];
  body?: { field: string; type: string; required: boolean; description: string }[];
  response?: string;
}

interface ApiSection {
  title: string;
  icon: React.ReactNode;
  endpoints: ApiEndpoint[];
}

const apiSections: ApiSection[] = [
  {
    title: 'Authentication',
    icon: <Lock className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/auth/login',
        description: 'Login',
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'password', type: 'string', required: true, description: 'Password' }
        ],
        response: `{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "admin",
    "email": "admin@baluhost.local",
    "role": "admin"
  }
}`
      },
      {
        method: 'POST',
        path: '/api/auth/register',
        description: 'Register',
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'email', type: 'string', required: true, description: 'Email address' },
          { field: 'password', type: 'string', required: true, description: 'Password' }
        ],
        response: `{
  "id": "uuid",
  "username": "newuser",
  "email": "user@example.com",
  "role": "user"
}`
      },
      {
        method: 'GET',
        path: '/api/auth/me',
        description: 'Read Current User',
        requiresAuth: true,
        response: `{
  "user": {
    "id": "uuid",
    "username": "admin",
    "email": "admin@baluhost.local",
    "role": "admin"
  }
}`
      },
      {
        method: 'POST',
        path: '/api/auth/logout',
        description: 'Logout',
        requiresAuth: true,
        response: `{
  "message": "Logged out successfully"
}`
      }
    ]
  },
  {
    title: 'Files',
    icon: <FileText className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/files/list',
        description: 'List Files',
        requiresAuth: true,
        params: [
          { name: 'path', type: 'string', required: false, description: 'Directory path (default: root)' }
        ],
        response: `{
  "files": [
    {
      "name": "document.pdf",
      "path": "/document.pdf",
      "size": 1048576,
      "is_directory": false,
      "modified": "2025-11-23T10:30:00",
      "owner": "admin",
      "permissions": "rw-r--r--"
    }
  ],
  "current_path": "/"
}`
      },
      {
        method: 'GET',
        path: '/api/files/download/{resource_path}',
        description: 'Download File',
        requiresAuth: true,
        params: [
          { name: 'resource_path', type: 'string', required: true, description: 'File path' }
        ],
        response: 'Binary file content'
      },
      {
        method: 'POST',
        path: '/api/files/upload',
        description: 'Upload File',
        requiresAuth: true,
        body: [
          { field: 'file', type: 'file', required: true, description: 'File to upload' },
          { field: 'path', type: 'string', required: false, description: 'Target directory path' }
        ],
        response: `{
  "filename": "uploaded.txt",
  "path": "/uploaded.txt",
  "size": 2048
}`
      },
      {
        method: 'GET',
        path: '/api/files/storage/available',
        description: 'Get Available Storage',
        requiresAuth: true,
        response: `{
  "total": 10737418240,
  "used": 5368709120,
  "available": 5368709120,
  "percent": 50.0
}`
      },
      {
        method: 'DELETE',
        path: '/api/files/{resource_path}',
        description: 'Delete Path',
        requiresAuth: true,
        params: [
          { name: 'resource_path', type: 'string', required: true, description: 'File or folder path' }
        ],
        response: `{
  "message": "Path deleted successfully"
}`
      },
      {
        method: 'POST',
        path: '/api/files/folder',
        description: 'Create Folder',
        requiresAuth: true,
        body: [
          { field: 'path', type: 'string', required: true, description: 'Folder path' }
        ],
        response: `{
  "path": "/new_folder",
  "message": "Folder created"
}`
      },
      {
        method: 'PUT',
        path: '/api/files/rename',
        description: 'Rename Path',
        requiresAuth: true,
        body: [
          { field: 'old_path', type: 'string', required: true, description: 'Current path' },
          { field: 'new_path', type: 'string', required: true, description: 'New path' }
        ],
        response: `{
  "old_path": "/old.txt",
  "new_path": "/new.txt",
  "message": "Path renamed"
}`
      },
      {
        method: 'PUT',
        path: '/api/files/move',
        description: 'Move Path',
        requiresAuth: true,
        body: [
          { field: 'source', type: 'string', required: true, description: 'Source path' },
          { field: 'destination', type: 'string', required: true, description: 'Destination path' }
        ],
        response: `{
  "source": "/file.txt",
  "destination": "/folder/file.txt",
  "message": "Path moved"
}`
      }
    ]
  },
  {
    title: 'Logging',
    icon: <Terminal className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/logging/disk-io',
        description: 'Get Disk-IO Logs',
        requiresAuth: true,
        params: [
          { name: 'limit', type: 'integer', required: false, description: 'Number of logs (default: 100)' }
        ],
        response: `{
  "logs": [
    {
      "timestamp": "2025-11-23T10:30:00",
      "operation": "read",
      "device": "/dev/sda1",
      "bytes": 4096,
      "duration_ms": 2.5
    }
  ]
}`
      },
      {
        method: 'GET',
        path: '/api/logging/file-access',
        description: 'Get File Access Logs',
        requiresAuth: true,
        params: [
          { name: 'limit', type: 'integer', required: false, description: 'Number of logs (default: 100)' }
        ],
        response: `{
  "logs": [
    {
      "timestamp": "2025-11-23T10:30:00",
      "user": "admin",
      "action": "download",
      "path": "/document.pdf",
      "success": true
    }
  ]
}`
      },
      {
        method: 'GET',
        path: '/api/logging/stats',
        description: 'Get Logging Stats',
        requiresAuth: true,
        response: `{
  "total_logs": 15234,
  "disk_io_logs": 8500,
  "file_access_logs": 4234,
  "security_logs": 2500
}`
      }
    ]
  },
  {
    title: 'System',
    icon: <Activity className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/system/info',
        description: 'Get System Info',
        requiresAuth: true,
        response: `{
  "hostname": "baluhost-nas",
  "os": "Linux",
  "os_version": "5.15.0",
  "architecture": "x86_64",
  "cpu_count": 8,
  "total_memory": 17179869184
}`
      },
      {
        method: 'GET',
        path: '/api/system/telemetry',
        description: 'Get System Telemetry',
        requiresAuth: true,
        response: `{
  "system": {
    "cpu_usage": 25.5,
    "cpu_cores": 8,
    "memory_used": 8589934592,
    "memory_total": 17179869184,
    "uptime": 86400
  },
  "storage": {
    "total": 10737418240,
    "used": 5368709120,
    "available": 5368709120,
    "percent": 50.0
  }
}`
      },
      {
        method: 'GET',
        path: '/api/system/raid/status',
        description: 'Get RAID Status',
        requiresAuth: true,
        response: `{
  "arrays": [
    {
      "device": "/dev/md0",
      "level": "RAID1",
      "state": "active",
      "devices": ["/dev/sda1", "/dev/sdb1"],
      "health": "clean"
    }
  ]
}`
      },
      {
        method: 'GET',
        path: '/api/system/smart',
        description: 'Get SMART Data',
        requiresAuth: true,
        response: `{
  "devices": [
    {
      "device": "/dev/sda",
      "model": "Samsung SSD 970 EVO",
      "serial": "S1234567890",
      "health": "PASSED",
      "temperature": 35,
      "power_on_hours": 8760
    }
  ]
}`
      },
      {
        method: 'POST',
        path: '/api/system/shutdown',
        description: 'Schedule Application Shutdown (Admin)',
        requiresAuth: true,
        response: `{
  "message": "Shutdown scheduled",
  "initiated_by": "admin",
  "eta_seconds": 3
}`
      }
    ]
  },
  {
    title: 'Users',
    icon: <Users className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/users/',
        description: 'List Users (Admin)',
        requiresAuth: true,
        params: [
          { name: 'search', type: 'string', required: false, description: 'Search by username or email' },
          { name: 'role', type: 'string', required: false, description: 'Filter by role' },
          { name: 'is_active', type: 'boolean', required: false, description: 'Filter by active status' },
          { name: 'sort_by', type: 'string', required: false, description: 'Sort field (default: created_at)' },
          { name: 'sort_order', type: 'string', required: false, description: 'Sort order: asc/desc' }
        ],
        response: `{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@baluhost.local",
      "role": "admin",
      "is_active": true,
      "created_at": "2025-11-23T10:30:00"
    }
  ],
  "total": 5,
  "active": 4,
  "inactive": 1,
  "admins": 1
}`
      },
      {
        method: 'POST',
        path: '/api/users/',
        description: 'Create User (Admin)',
        requiresAuth: true,
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'email', type: 'string', required: true, description: 'Email address' },
          { field: 'password', type: 'string', required: true, description: 'Password' },
          { field: 'role', type: 'string', required: false, description: 'Role: admin/user (default: user)' }
        ],
        response: `{
  "id": 2,
  "username": "newuser",
  "email": "user@example.com",
  "role": "user",
  "is_active": true
}`
      },
      {
        method: 'PUT',
        path: '/api/users/{user_id}',
        description: 'Update User (Admin)',
        requiresAuth: true,
        params: [
          { name: 'user_id', type: 'string', required: true, description: 'User ID' }
        ],
        body: [
          { field: 'email', type: 'string', required: false, description: 'New email' },
          { field: 'role', type: 'string', required: false, description: 'New role' },
          { field: 'is_active', type: 'boolean', required: false, description: 'Active status' }
        ],
        response: `{
  "id": 2,
  "username": "user",
  "email": "updated@example.com",
  "role": "user"
}`
      },
      {
        method: 'DELETE',
        path: '/api/users/{user_id}',
        description: 'Delete User (Admin)',
        requiresAuth: true,
        params: [
          { name: 'user_id', type: 'string', required: true, description: 'User ID' }
        ],
        response: '204 No Content'
      },
      {
        method: 'POST',
        path: '/api/users/{user_id}/avatar',
        description: 'Upload User Avatar',
        requiresAuth: true,
        params: [
          { name: 'user_id', type: 'string', required: true, description: 'User ID' }
        ],
        body: [
          { field: 'avatar', type: 'file', required: true, description: 'Image file (JPEG, PNG, GIF, WebP)' }
        ],
        response: `{
  "id": 1,
  "username": "admin",
  "avatar_url": "/avatars/abc123.png"
}`
      }
    ]
  },
  {
    title: 'Shares',
    icon: <Share2 className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/shares/links',
        description: 'Create Public Share Link',
        requiresAuth: true,
        body: [
          { field: 'file_id', type: 'integer', required: true, description: 'File ID to share' },
          { field: 'password', type: 'string', required: false, description: 'Optional password protection' },
          { field: 'expires_at', type: 'datetime', required: false, description: 'Expiration date' },
          { field: 'max_downloads', type: 'integer', required: false, description: 'Max download limit' },
          { field: 'allow_download', type: 'boolean', required: false, description: 'Allow downloads' },
          { field: 'allow_preview', type: 'boolean', required: false, description: 'Allow preview' },
          { field: 'description', type: 'string', required: false, description: 'Share description' }
        ],
        response: `{
  "id": 1,
  "token": "abc123xyz",
  "file_id": 5,
  "has_password": true,
  "allow_download": true,
  "expires_at": "2025-12-31T23:59:59",
  "file_name": "document.pdf",
  "created_at": "2025-11-23T10:30:00"
}`
      },
      {
        method: 'GET',
        path: '/api/shares/links',
        description: 'List My Share Links',
        requiresAuth: true,
        params: [
          { name: 'include_expired', type: 'boolean', required: false, description: 'Include expired links' }
        ],
        response: `[
  {
    "id": 1,
    "token": "abc123",
    "file_name": "document.pdf",
    "download_count": 5,
    "max_downloads": 10,
    "is_expired": false,
    "created_at": "2025-11-23T10:30:00"
  }
]`
      },
      {
        method: 'DELETE',
        path: '/api/shares/links/{link_id}',
        description: 'Delete Share Link',
        requiresAuth: true,
        params: [
          { name: 'link_id', type: 'integer', required: true, description: 'Share link ID' }
        ],
        response: '204 No Content'
      },
      {
        method: 'POST',
        path: '/api/shares/user-shares',
        description: 'Share File With User',
        requiresAuth: true,
        body: [
          { field: 'file_id', type: 'integer', required: true, description: 'File ID' },
          { field: 'shared_with_user_id', type: 'integer', required: true, description: 'Target user ID' },
          { field: 'can_read', type: 'boolean', required: false, description: 'Read permission (default: true)' },
          { field: 'can_write', type: 'boolean', required: false, description: 'Write permission' },
          { field: 'can_delete', type: 'boolean', required: false, description: 'Delete permission' },
          { field: 'expires_at', type: 'datetime', required: false, description: 'Expiration date' }
        ],
        response: `{
  "id": 1,
  "file_id": 5,
  "file_name": "project.zip",
  "shared_with_username": "colleague",
  "can_read": true,
  "can_write": false,
  "created_at": "2025-11-23T10:30:00"
}`
      },
      {
        method: 'GET',
        path: '/api/shares/shared-with-me',
        description: 'Get Files Shared With Me',
        requiresAuth: true,
        response: `[
  {
    "share_id": 1,
    "file_id": 5,
    "file_name": "report.pdf",
    "owner_username": "boss",
    "can_read": true,
    "can_write": false,
    "shared_at": "2025-11-23T10:30:00"
  }
]`
      },
      {
        method: 'GET',
        path: '/api/shares/public/{token}/info',
        description: 'Get Public Share Info (No Auth)',
        requiresAuth: false,
        params: [
          { name: 'token', type: 'string', required: true, description: 'Share token from URL' }
        ],
        response: `{
  "has_password": true,
  "is_accessible": true,
  "file_name": "document.pdf",
  "file_size": 1048576,
  "expires_at": "2025-12-31T23:59:59"
}`
      }
    ]
  },
  {
    title: 'Backup',
    icon: <Database className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/backups/',
        description: 'Create Backup (Admin)',
        requiresAuth: true,
        body: [
          { field: 'includes_database', type: 'boolean', required: false, description: 'Include database (default: true)' },
          { field: 'includes_files', type: 'boolean', required: false, description: 'Include files (default: true)' },
          { field: 'includes_config', type: 'boolean', required: false, description: 'Include config (default: true)' },
          { field: 'description', type: 'string', required: false, description: 'Backup description' }
        ],
        response: `{
  "id": 1,
  "filename": "backup_20251123_103000.tar.gz",
  "size_bytes": 524288000,
  "includes_database": true,
  "includes_files": true,
  "created_at": "2025-11-23T10:30:00",
  "creator": "admin"
}`
      },
      {
        method: 'GET',
        path: '/api/backups/',
        description: 'List Backups (Admin)',
        requiresAuth: true,
        response: `{
  "backups": [
    {
      "id": 1,
      "filename": "backup_20251123_103000.tar.gz",
      "size_bytes": 524288000,
      "created_at": "2025-11-23T10:30:00"
    }
  ],
  "total_size_bytes": 524288000,
  "total_size_mb": 500
}`
      },
      {
        method: 'POST',
        path: '/api/backups/{backup_id}/restore',
        description: 'Restore Backup (Admin)',
        requiresAuth: true,
        params: [
          { name: 'backup_id', type: 'integer', required: true, description: 'Backup ID' }
        ],
        body: [
          { field: 'backup_id', type: 'integer', required: true, description: 'Backup ID (must match)' },
          { field: 'confirm', type: 'boolean', required: true, description: 'Must be true to proceed' },
          { field: 'restore_database', type: 'boolean', required: false, description: 'Restore database' },
          { field: 'restore_files', type: 'boolean', required: false, description: 'Restore files' },
          { field: 'restore_config', type: 'boolean', required: false, description: 'Restore config' }
        ],
        response: `{
  "success": true,
  "message": "Backup restored successfully. Please restart the application.",
  "backup_id": 1,
  "restored_at": "2025-11-23T10:45:00"
}`
      },
      {
        method: 'GET',
        path: '/api/backups/{backup_id}/download',
        description: 'Download Backup File (Admin)',
        requiresAuth: true,
        params: [
          { name: 'backup_id', type: 'integer', required: true, description: 'Backup ID' }
        ],
        response: 'Binary tar.gz file'
      },
      {
        method: 'DELETE',
        path: '/api/backups/{backup_id}',
        description: 'Delete Backup (Admin)',
        requiresAuth: true,
        params: [
          { name: 'backup_id', type: 'integer', required: true, description: 'Backup ID' }
        ],
        response: '204 No Content'
      }
    ]
  },
  {
    title: 'Mobile Devices',
    icon: <Smartphone className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/mobile/token/generate',
        description: 'Generate QR Registration Token (Localhost Only)',
        requiresAuth: true,
        params: [
          { name: 'include_vpn', type: 'boolean', required: false, description: 'Include VPN config in QR code' },
          { name: 'device_name', type: 'string', required: false, description: 'Device name (default: iOS Device)' },
          { name: 'token_validity_days', type: 'integer', required: false, description: 'Token validity 30-180 days (default: 90)' }
        ],
        response: `{
  "registration_token": "reg_abc123...",
  "qr_data": "baluhost://register?token=...",
  "expires_at": "2025-11-23T10:35:00",
  "server_url": "http://192.168.1.100:8000"
}`
      },
      {
        method: 'POST',
        path: '/api/mobile/register',
        description: 'Register Mobile Device (Called by App)',
        requiresAuth: false,
        body: [
          { field: 'registration_token', type: 'string', required: true, description: 'Token from QR code' },
          { field: 'device_name', type: 'string', required: true, description: 'Device name' },
          { field: 'device_model', type: 'string', required: false, description: 'Device model' },
          { field: 'os_version', type: 'string', required: false, description: 'OS version' }
        ],
        response: `{
  "access_token": "mobile_token_abc...",
  "device_id": "uuid-1234",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@baluhost.local"
  },
  "expires_at": "2026-02-23T10:30:00"
}`
      },
      {
        method: 'GET',
        path: '/api/mobile/devices',
        description: 'List My Mobile Devices',
        requiresAuth: true,
        response: `[
  {
    "id": "uuid-1234",
    "device_name": "iPhone 15 Pro",
    "device_model": "iPhone15,2",
    "os_version": "iOS 17.2",
    "is_active": true,
    "last_seen": "2025-11-23T10:30:00",
    "registered_at": "2025-11-20T15:00:00"
  }
]`
      },
      {
        method: 'DELETE',
        path: '/api/mobile/devices/{device_id}',
        description: 'Delete Mobile Device',
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'string', required: true, description: 'Device ID' }
        ],
        response: '204 No Content'
      },
      {
        method: 'POST',
        path: '/api/mobile/devices/{device_id}/push-token',
        description: 'Register FCM Push Token',
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'string', required: true, description: 'Device ID' },
          { name: 'push_token', type: 'string', required: true, description: 'Firebase Cloud Messaging token' }
        ],
        response: `{
  "success": true,
  "device_id": "uuid-1234",
  "token_verified": true
}`
      }
    ]
  },
  {
    title: 'VPN',
    icon: <Wifi className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/vpn/generate-config',
        description: 'Generate WireGuard VPN Config',
        requiresAuth: true,
        body: [
          { field: 'device_name', type: 'string', required: true, description: 'Device name for VPN client' },
          { field: 'server_public_endpoint', type: 'string', required: true, description: 'Public IP/domain:port' }
        ],
        response: `{
  "config_file": "[Interface]\\nPrivateKey = ...\\n[Peer]\\n...",
  "qr_code_data": "[Interface]\\n...",
  "client_id": 1,
  "client_ip": "10.0.0.2"
}`
      },
      {
        method: 'GET',
        path: '/api/vpn/clients',
        description: 'List My VPN Clients',
        requiresAuth: true,
        response: `[
  {
    "id": 1,
    "device_name": "iPhone",
    "client_ip": "10.0.0.2",
    "is_active": true,
    "last_handshake": "2025-11-23T10:30:00",
    "created_at": "2025-11-20T15:00:00"
  }
]`
      },
      {
        method: 'DELETE',
        path: '/api/vpn/clients/{client_id}',
        description: 'Delete VPN Client',
        requiresAuth: true,
        params: [
          { name: 'client_id', type: 'integer', required: true, description: 'Client ID' }
        ],
        response: '204 No Content'
      },
      {
        method: 'POST',
        path: '/api/vpn/fritzbox/upload',
        description: 'Upload Fritz!Box WireGuard Config (Admin)',
        requiresAuth: true,
        body: [
          { field: 'config_content', type: 'string', required: true, description: 'WireGuard .conf file content' },
          { field: 'public_endpoint', type: 'string', required: true, description: 'Public IP/domain for endpoint' }
        ],
        response: `{
  "id": 1,
  "endpoint": "vpn.example.com:51820",
  "config_base64": "W0ludGVyZmFjZV0...",
  "is_active": true
}`
      },
      {
        method: 'GET',
        path: '/api/vpn/fritzbox/qr',
        description: 'Get Fritz!Box Config as QR Code Data',
        requiresAuth: true,
        response: `{
  "config_base64": "W0ludGVyZmFjZV0..."
}`
      }
    ]
  },
  {
    title: 'Power Management',
    icon: <Zap className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/power/status',
        description: 'Get Current Power Status',
        requiresAuth: true,
        response: `{
  "current_profile": "performance",
  "cpu_freq_mhz": 3800,
  "active_demands": ["raid_resync"],
  "auto_scaling_enabled": true,
  "override_until": null
}`
      },
      {
        method: 'GET',
        path: '/api/power/profiles',
        description: 'Get Available Power Profiles',
        requiresAuth: true,
        response: `{
  "profiles": [
    {
      "name": "powersave",
      "governor": "powersave",
      "epp": "power",
      "min_freq_mhz": 800,
      "max_freq_mhz": 2400
    },
    {
      "name": "balanced",
      "governor": "powersave",
      "epp": "balance_performance",
      "min_freq_mhz": 800,
      "max_freq_mhz": 3800
    },
    {
      "name": "performance",
      "governor": "performance",
      "epp": "performance",
      "min_freq_mhz": 3800,
      "max_freq_mhz": 3800
    }
  ],
  "current_profile": "balanced"
}`
      },
      {
        method: 'POST',
        path: '/api/power/profile',
        description: 'Set Power Profile (Admin)',
        requiresAuth: true,
        body: [
          { field: 'profile', type: 'string', required: true, description: 'Profile name: powersave/balanced/performance' },
          { field: 'reason', type: 'string', required: false, description: 'Reason for change' },
          { field: 'duration_seconds', type: 'integer', required: false, description: 'Override duration (null = permanent)' }
        ],
        response: `{
  "success": true,
  "previous_profile": "balanced",
  "new_profile": "performance",
  "applied_at": "2025-11-23T10:30:00"
}`
      },
      {
        method: 'POST',
        path: '/api/power/demand/register',
        description: 'Register Power Demand',
        requiresAuth: true,
        body: [
          { field: 'source', type: 'string', required: true, description: 'Demand source (e.g., "raid_resync")' },
          { field: 'reason', type: 'string', required: false, description: 'Human-readable reason' },
          { field: 'duration_seconds', type: 'integer', required: false, description: 'Expected duration' }
        ],
        response: `{
  "success": true,
  "demand_id": "demand_abc123",
  "profile_changed": true,
  "new_profile": "performance"
}`
      },
      {
        method: 'POST',
        path: '/api/power/demand/unregister',
        description: 'Unregister Power Demand',
        requiresAuth: true,
        body: [
          { field: 'demand_id', type: 'string', required: true, description: 'Demand ID from register' }
        ],
        response: `{
  "success": true,
  "profile_changed": false
}`
      }
    ]
  },
  {
    title: 'Energy Monitoring',
    icon: <Shield className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/energy/dashboard/{device_id}',
        description: 'Get Energy Dashboard for Device',
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'integer', required: true, description: 'Device ID (e.g., Tapo smart plug)' }
        ],
        response: `{
  "device_id": 1,
  "device_name": "Tapo Plug",
  "current_watts": 4.2,
  "is_online": true,
  "hourly_samples": [
    {
      "hour": "2026-01-24T01:00:00Z",
      "avg_watts": 3.5
    }
  ]
}`
      },
      {
        method: 'GET',
        path: '/api/energy/hourly/{device_id}',
        description: 'Get Hourly Power Samples',
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'integer', required: true, description: 'Device ID' },
          { name: 'hours', type: 'integer', required: false, description: 'Hours of history (default: 24)' }
        ],
        response: `[
  {
    "timestamp": "2026-01-24T01:00:00Z",
    "avg_watts": 3.5,
    "min_watts": 2.1,
    "max_watts": 5.8
  }
]`
      },
      {
        method: 'GET',
        path: '/api/energy/cost/{device_id}',
        description: 'Estimate Energy Cost',
        requiresAuth: true,
        params: [
          { name: 'device_id', type: 'integer', required: true, description: 'Device ID' },
          { name: 'period', type: 'string', required: false, description: 'Period: today/week/month' },
          { name: 'cost_per_kwh', type: 'float', required: false, description: 'Cost per kWh (e.g., 0.40)' }
        ],
        response: `{
  "period": "today",
  "kwh_consumed": 0.15,
  "cost": 0.06,
  "currency": "EUR"
}`
      }
    ]
  }
];

const methodColors = {
  GET: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  POST: 'bg-green-500/20 text-green-400 border-green-500/30',
  PUT: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  DELETE: 'bg-red-500/20 text-red-400 border-red-500/30'
};

function EndpointCard({ endpoint }: { endpoint: ApiEndpoint }) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="card mb-3 sm:mb-4">
      <div
        className="flex items-start sm:items-center justify-between cursor-pointer min-h-[44px] touch-manipulation"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`px-2 sm:px-3 py-1 rounded-lg text-[10px] sm:text-xs font-bold border ${methodColors[endpoint.method]}`}>
              {endpoint.method}
            </span>
            {endpoint.requiresAuth && (
              <span title="Requires authentication" className="sm:hidden"><Shield className="w-4 h-4 text-sky-400" /></span>
            )}
          </div>
          <code className="text-slate-300 font-mono text-xs sm:text-sm break-all">{endpoint.path}</code>
          <span className="text-slate-400 text-xs sm:text-sm hidden md:inline">{endpoint.description}</span>
          {endpoint.requiresAuth && (
            <span title="Requires authentication" className="hidden sm:inline"><Shield className="w-4 h-4 text-sky-400" /></span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="w-5 h-5 text-slate-400 flex-shrink-0 ml-2" />
        ) : (
          <ChevronRight className="w-5 h-5 text-slate-400 flex-shrink-0 ml-2" />
        )}
      </div>

      {isOpen && (
        <div className="mt-4 space-y-4">
          {endpoint.params && endpoint.params.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-slate-300 mb-2">Parameters</h4>
              <div className="space-y-2">
                {endpoint.params.map((param, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-sm">
                    <code className="text-sky-400 font-mono">{param.name}</code>
                    <span className="text-slate-500">({param.type})</span>
                    {param.required && (
                      <span className="text-red-400 text-xs">required</span>
                    )}
                    <span className="text-slate-400">{param.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.body && endpoint.body.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-slate-300 mb-2">Request Body</h4>
              <div className="space-y-2">
                {endpoint.body.map((field, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-sm">
                    <code className="text-violet-400 font-mono">{field.field}</code>
                    <span className="text-slate-500">({field.type})</span>
                    {field.required && (
                      <span className="text-red-400 text-xs">required</span>
                    )}
                    <span className="text-slate-400">{field.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.response && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-slate-300">Response Example</h4>
                <button
                  onClick={() => copyToClipboard(endpoint.response!)}
                  className="text-slate-400 hover:text-sky-400 transition-colors p-1"
                >
                  {copied ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
              <pre className="bg-slate-950/60 border border-slate-800 rounded-lg p-4 text-xs overflow-x-auto">
                <code className="text-slate-300">{endpoint.response}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ApiDocs() {
  const { t } = useTranslation(['apiDocs', 'common']);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [showAuth, setShowAuth] = useState(false);
  const [tokenInput, setTokenInput] = useState('');
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem('token');
    if (t) {
      setAuthorized(true);
      setTokenInput(t);
    }
  }, []);

  const openAuth = () => setShowAuth(true);
  const closeAuth = () => setShowAuth(false);
  const saveAuth = () => {
    const v = tokenInput.trim();
    if (!v) return;
    localStorage.setItem('token', v);
    setAuthorized(true);
    setShowAuth(false);
  };

  const clearAuth = () => {
    localStorage.removeItem('token');
    setAuthorized(false);
    setTokenInput('');
    setShowAuth(false);
  };

  const filteredSections = selectedSection
    ? apiSections.filter(s => s.title === selectedSection)
    : apiSections;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-r from-sky-400 via-indigo-400 to-violet-400 bg-clip-text text-transparent">
            {t('title')}
          </h1>
          <p className="text-slate-400 mt-1 sm:mt-2 text-xs sm:text-sm">
            {t('subtitle')}
          </p>
        </div>
        <>
          <button className="btn btn-primary min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={openAuth}>
            {authorized ? (
              <Check className="w-4 h-4 text-green-300" />
            ) : (
              <Lock className="w-4 h-4" />
            )}
            <span className="ml-2">{authorized ? t('authorize.authorized') : t('authorize.button')}</span>
          </button>

          {showAuth && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
              <div className="absolute inset-0 bg-black/60" onClick={closeAuth} />
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 sm:p-6 w-full max-w-lg z-10 max-h-[90vh] overflow-y-auto">
                <h3 className="text-base sm:text-lg font-semibold text-slate-100 mb-3">{t('authorize.title')}</h3>
                <p className="text-xs sm:text-sm text-slate-400 mb-3">{t('authorize.description')}</p>
                <input
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder={t('authorize.placeholder')}
                  className="w-full bg-slate-950/60 border border-slate-800 rounded px-3 py-2.5 text-sm text-slate-200 mb-4 min-h-[44px]"
                />
                <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
                  <button className="btn btn-secondary min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={clearAuth}>{t('authorize.clear')}</button>
                  <button className="btn min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={closeAuth}>{t('authorize.cancel')}</button>
                  <button className="btn btn-primary min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={saveAuth}>{t('authorize.save')}</button>
                </div>
              </div>
            </div>
          )}
        </>
      </div>

      {/* Info Card */}
      <div className="glass-accent border-l-4 border-l-sky-500">
        <div className="flex items-start gap-3">
          <Code className="w-5 h-5 text-sky-400 mt-0.5" />
          <div>
            <h3 className="font-semibold text-slate-200 mb-1">{t('baseUrl.title')}</h3>
            <code className="text-sm text-sky-400 bg-slate-950/60 px-3 py-1 rounded">
              http://localhost:8000
            </code>
            <p className="text-sm text-slate-400 mt-2">
              {t('baseUrl.authInfo')}
            </p>
            <code className="text-xs text-slate-300 bg-slate-950/60 px-3 py-1 rounded mt-2 inline-block">
              Authorization: Bearer {"<"}access_token{">"}
            </code>
          </div>
        </div>
      </div>

      {/* Section Filter */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 pb-2">
        <div className="flex gap-2 min-w-max sm:flex-wrap sm:min-w-0">
          <button
            onClick={() => setSelectedSection(null)}
            className={`btn min-h-[44px] whitespace-nowrap touch-manipulation active:scale-95 transition-transform ${!selectedSection ? 'btn-primary' : 'btn-secondary'}`}
          >
            {t('filters.allEndpoints')}
          </button>
          {apiSections.map((section) => (
            <button
              key={section.title}
              onClick={() => setSelectedSection(section.title)}
              className={`btn min-h-[44px] whitespace-nowrap touch-manipulation active:scale-95 transition-transform ${selectedSection === section.title ? 'btn-primary' : 'btn-secondary'}`}
            >
              {section.icon}
              <span className="hidden sm:inline ml-1">{section.title}</span>
            </button>
          ))}
        </div>
      </div>

      {/* API Sections */}
      {filteredSections.map((section) => (
        <div key={section.title}>
          <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
            <div className="glow-ring p-1.5 sm:p-2">
              {section.icon}
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-slate-100">{section.title}</h2>
          </div>
          <div className="space-y-2 sm:space-y-3">
            {section.endpoints.map((endpoint, idx) => (
              <EndpointCard key={idx} endpoint={endpoint} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

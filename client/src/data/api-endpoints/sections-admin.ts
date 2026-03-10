import { createElement } from 'react';
import { Settings, HardDrive, ShieldCheck, Heart, BarChart, Key, ScrollText, Wrench } from 'lucide-react';
import type { ApiSection } from './types';

const icon = (Icon: React.ComponentType<{ className?: string }>) =>
  createElement(Icon, { className: 'w-5 h-5' });

export const adminSections: ApiSection[] = [
  {
    title: 'Admin Services',
    icon: icon(Settings),
    endpoints: [
      { method: 'GET', path: '/api/admin/services', description: 'List All Services (Admin)', requiresAuth: true, response: '[{ "name": "telemetry", "state": "running", "uptime_seconds": 86400 }]' },
      {
        method: 'GET',
        path: '/api/admin/services/{service_name}',
        description: 'Get Service Detail (Admin)',
        requiresAuth: true,
        params: [{ name: 'service_name', type: 'string', required: true, description: 'Service name' }],
        response: '{ "name": "telemetry", "state": "running", "uptime_seconds": 86400, "sample_count": 28800 }',
      },
      {
        method: 'POST',
        path: '/api/admin/services/{service_name}/start',
        description: 'Start Service (Admin)',
        requiresAuth: true,
        params: [{ name: 'service_name', type: 'string', required: true, description: 'Service name' }],
        response: '{ "success": true, "previous_state": "stopped", "current_state": "running" }',
      },
      {
        method: 'POST',
        path: '/api/admin/services/{service_name}/stop',
        description: 'Stop Service (Admin)',
        requiresAuth: true,
        params: [{ name: 'service_name', type: 'string', required: true, description: 'Service name' }],
        response: '{ "success": true, "previous_state": "running", "current_state": "stopped" }',
      },
      {
        method: 'POST',
        path: '/api/admin/services/{service_name}/restart',
        description: 'Restart Service (Admin)',
        requiresAuth: true,
        params: [{ name: 'service_name', type: 'string', required: true, description: 'Service name' }],
        body: [{ field: 'force', type: 'boolean', required: false, description: 'Force restart' }],
        response: '{ "success": true, "previous_state": "running", "current_state": "running" }',
      },
      { method: 'GET', path: '/api/admin/dependencies', description: 'Get System Dependencies (Admin)', requiresAuth: true, response: '[{ "name": "mdadm", "available": true, "version": "4.2" }]' },
      { method: 'GET', path: '/api/admin/metrics', description: 'Get Application Metrics (Admin)', requiresAuth: true, response: '{ "uptime_seconds": 86400, "memory_mb": 256, "error_count": 0 }' },
      { method: 'GET', path: '/api/admin/debug', description: 'Get Debug Snapshot (Admin)', requiresAuth: true, response: '{ "services": [...], "dependencies": [...], "metrics": {...} }' },
    ],
  },
  {
    title: 'Admin Database',
    icon: icon(HardDrive),
    endpoints: [
      { method: 'GET', path: '/api/admin/db/tables', description: 'List Database Tables (Admin)', requiresAuth: true, response: '{ "tables": ["users", "file_metadata", "shares", ...] }' },
      { method: 'GET', path: '/api/admin/db/tables/categories', description: 'Get Table Categories (Admin)', requiresAuth: true, response: '{ "core": ["users", "file_metadata"], "monitoring": ["cpu_samples", ...] }' },
      {
        method: 'GET',
        path: '/api/admin/db/table/{table_name}/schema',
        description: 'Get Table Schema (Admin)',
        requiresAuth: true,
        params: [{ name: 'table_name', type: 'string', required: true, description: 'Table name' }],
        response: '{ "columns": [{ "name": "id", "type": "INTEGER", "nullable": false }] }',
      },
      {
        method: 'GET',
        path: '/api/admin/db/table/{table_name}',
        description: 'Get Table Rows (Admin)',
        requiresAuth: true,
        params: [
          { name: 'table_name', type: 'string', required: true, description: 'Table name' },
          { name: 'limit', type: 'integer', required: false, description: 'Row limit (default: 50)' },
          { name: 'offset', type: 'integer', required: false, description: 'Row offset' },
        ],
        response: '{ "rows": [...], "total": 100, "columns": [...] }',
      },
      { method: 'GET', path: '/api/admin/db/health', description: 'Get Database Health (Admin)', requiresAuth: true, response: '{ "status": "healthy", "size_bytes": 52428800 }' },
      { method: 'GET', path: '/api/admin/db/info', description: 'Get Database Info (Admin)', requiresAuth: true, response: '{ "engine": "postgresql", "version": "17.7", "tables": 25 }' },
    ],
  },
  {
    title: 'Rate Limits',
    icon: icon(ShieldCheck),
    endpoints: [
      { method: 'GET', path: '/api/admin/rate-limits', description: 'List Rate Limit Configs (Admin)', requiresAuth: true, response: '[{ "endpoint_type": "auth", "requests_per_minute": 10 }]' },
      {
        method: 'GET',
        path: '/api/admin/rate-limits/{endpoint_type}',
        description: 'Get Rate Limit Config (Admin)',
        requiresAuth: true,
        params: [{ name: 'endpoint_type', type: 'string', required: true, description: 'Endpoint type' }],
        response: '{ "endpoint_type": "auth", "requests_per_minute": 10 }',
      },
      {
        method: 'POST',
        path: '/api/admin/rate-limits',
        description: 'Create Rate Limit Config (Admin)',
        requiresAuth: true,
        body: [
          { field: 'endpoint_type', type: 'string', required: true, description: 'Endpoint type' },
          { field: 'requests_per_minute', type: 'integer', required: true, description: 'Requests per minute' },
        ],
        response: '{ "endpoint_type": "files", "requests_per_minute": 60 }',
      },
      {
        method: 'PUT',
        path: '/api/admin/rate-limits/{endpoint_type}',
        description: 'Update Rate Limit Config (Admin)',
        requiresAuth: true,
        params: [{ name: 'endpoint_type', type: 'string', required: true, description: 'Endpoint type' }],
        response: '{ "endpoint_type": "auth", "requests_per_minute": 20 }',
      },
      {
        method: 'DELETE',
        path: '/api/admin/rate-limits/{endpoint_type}',
        description: 'Delete Rate Limit Config (Admin)',
        requiresAuth: true,
        params: [{ name: 'endpoint_type', type: 'string', required: true, description: 'Endpoint type' }],
        response: '204 No Content',
      },
      { method: 'POST', path: '/api/admin/rate-limits/seed-defaults', description: 'Seed Default Rate Limits (Admin)', requiresAuth: true, response: '204 No Content' },
    ],
  },
  {
    title: 'API Keys',
    icon: icon(Key),
    endpoints: [
      {
        method: 'POST',
        path: '/api/api-keys',
        description: 'Create API Key (Admin)',
        requiresAuth: true,
        body: [
          { field: 'name', type: 'string', required: true, description: 'Key name/label' },
          { field: 'target_user_id', type: 'integer', required: true, description: 'User the key acts as' },
          { field: 'expires_in_days', type: 'integer', required: false, description: 'Expiry in days (null = never)' },
        ],
        response: '{ "id": 1, "name": "CI Pipeline", "key": "bh_abc123...", "key_prefix": "bh_abc1", "expires_at": "2026-06-01T00:00:00" }',
      },
      { method: 'GET', path: '/api/api-keys', description: 'List API Keys (Admin)', requiresAuth: true, response: '{ "keys": [{ "id": 1, "name": "CI Pipeline", "key_prefix": "bh_abc1", "is_active": true, "use_count": 42 }], "total": 1 }' },
      { method: 'GET', path: '/api/api-keys/eligible-users', description: 'Get Eligible Users (Admin)', requiresAuth: true, response: '[{ "id": 1, "username": "admin", "role": "admin" }, { "id": 2, "username": "user1", "role": "user" }]' },
      {
        method: 'GET',
        path: '/api/api-keys/{key_id}',
        description: 'Get API Key Detail (Admin)',
        requiresAuth: true,
        params: [{ name: 'key_id', type: 'integer', required: true, description: 'API key ID' }],
        response: '{ "id": 1, "name": "CI Pipeline", "key_prefix": "bh_abc1", "is_active": true, "use_count": 42, "last_used_at": "..." }',
      },
      {
        method: 'DELETE',
        path: '/api/api-keys/{key_id}',
        description: 'Revoke API Key (Admin)',
        requiresAuth: true,
        params: [{ name: 'key_id', type: 'integer', required: true, description: 'API key ID' }],
        response: '{ "detail": "API key revoked successfully" }',
      },
    ],
  },
  {
    title: 'Backend Logs',
    icon: icon(ScrollText),
    endpoints: [
      {
        method: 'GET',
        path: '/api/admin/backend-logs',
        description: 'Get Buffered Backend Logs (Admin)',
        requiresAuth: true,
        params: [
          { name: 'since_id', type: 'integer', required: false, description: 'Return entries with id > since_id' },
          { name: 'level', type: 'string', required: false, description: 'Min log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)' },
          { name: 'search', type: 'string', required: false, description: 'Case-insensitive substring search' },
          { name: 'limit', type: 'integer', required: false, description: 'Max entries (default: 200, max: 1000)' },
        ],
        response: '{ "entries": [{ "id": 1, "timestamp": "...", "level": "INFO", "message": "...", "logger": "app.main" }], "latest_id": 100, "total_buffered": 500 }',
      },
      {
        method: 'GET',
        path: '/api/admin/backend-logs/stream',
        description: 'Stream Backend Logs (SSE, Admin)',
        requiresAuth: true,
        params: [
          { name: 'token', type: 'string', required: true, description: 'Admin JWT token (query param for SSE)' },
          { name: 'level', type: 'string', required: false, description: 'Min log level filter' },
        ],
        response: 'Server-Sent Events stream (event: log, data: { id, timestamp, level, message })',
      },
      { method: 'DELETE', path: '/api/admin/backend-logs', description: 'Clear Backend Log Buffer (Admin)', requiresAuth: true, response: '{ "cleared": 500 }' },
    ],
  },
  {
    title: 'Environment Config',
    icon: icon(Wrench),
    endpoints: [
      {
        method: 'GET',
        path: '/api/env-config',
        description: 'Read Environment Variables (Admin)',
        requiresAuth: true,
        response: '{ "backend": [{ "key": "SECRET_KEY", "value": "••••••••", "sensitive": true }], "client": [...] }',
      },
      {
        method: 'PUT',
        path: '/api/env-config',
        description: 'Update Environment Variables (Admin)',
        requiresAuth: true,
        body: [
          { field: 'file', type: 'string', required: true, description: 'File: backend/client' },
          { field: 'updates', type: 'array', required: true, description: 'Array of { key, value } updates' },
        ],
        response: '{ "changed": ["SOME_KEY"], "count": 1 }',
      },
      {
        method: 'GET',
        path: '/api/env-config/reveal/{key}',
        description: 'Reveal Sensitive Variable (Admin)',
        requiresAuth: true,
        params: [{ name: 'key', type: 'string', required: true, description: 'Environment variable key' }],
        response: '{ "key": "SECRET_KEY", "value": "actual-secret-value" }',
      },
    ],
  },
  {
    title: 'Health',
    icon: icon(Heart),
    endpoints: [
      { method: 'GET', path: '/api/health', description: 'Health Check', requiresAuth: false, response: '{ "status": "healthy" }' },
      { method: 'GET', path: '/api/ping', description: 'Ping', requiresAuth: false, response: '{ "status": "pong" }' },
    ],
  },
  {
    title: 'Metrics',
    icon: icon(BarChart),
    endpoints: [
      { method: 'GET', path: '/api/metrics', description: 'Prometheus Metrics', requiresAuth: false, response: '# HELP baluhost_requests_total ...\nbaluhost_requests_total 12345' },
    ],
  },
];

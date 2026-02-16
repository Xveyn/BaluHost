import { createElement } from 'react';
import { Settings, HardDrive, ShieldCheck, Heart, BarChart } from 'lucide-react';
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

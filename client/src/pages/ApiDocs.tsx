import { useState, useEffect } from 'react';
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
  Check
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
        method: 'POST',
        path: '/api/system/shutdown',
        description: 'Schedule a graceful application shutdown (admin only). Returns ETA in seconds',
        requiresAuth: true,
        response: `{
  "message": "Shutdown scheduled",
  "initiated_by": "admin",
  "eta_seconds": 3
}`
      },
      {
        method: 'GET',
        path: '/api/system/info',
        description: 'Get system information and status',
        requiresAuth: true
      }
    ]
  },
  {
    title: 'Energy / Power Monitor',
    icon: <Shield className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/energy/dashboard/{device_id}',
        description: 'Get energy dashboard for a device (e.g. smart plug)',
        requiresAuth: true,
        response: `{
  "device_id": 1,
  "device_name": "Tapo Plug",
  "current_watts": 4.2,
  "is_online": true,
  "hourly_samples": [ { "hour": "2026-01-24T01:00:00Z", "avg_watts": 3.5 } ]
}`
      },
      {
        method: 'GET',
        path: '/api/energy/hourly/{device_id}?hours=24',
        description: 'Hourly averaged power samples for the given device (useful for charting)',
        requiresAuth: true
      },
      {
        method: 'GET',
        path: '/api/energy/cost/{device_id}?period=today&cost_per_kwh=0.40',
        description: 'Estimate cost for given period',
        requiresAuth: true
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
    <div className="card mb-4">
      <div 
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-3 flex-1">
          <span className={`px-3 py-1 rounded-lg text-xs font-bold border ${methodColors[endpoint.method]}`}>
            {endpoint.method}
          </span>
          <code className="text-slate-300 font-mono text-sm">{endpoint.path}</code>
          <span className="text-slate-400 text-sm">{endpoint.description}</span>
          {endpoint.requiresAuth && (
            <span title="Requires authentication"><Shield className="w-4 h-4 text-sky-400" /></span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="w-5 h-5 text-slate-400" />
        ) : (
          <ChevronRight className="w-5 h-5 text-slate-400" />
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-sky-400 via-indigo-400 to-violet-400 bg-clip-text text-transparent">
            Baluhost NAS API
          </h1>
          <p className="text-slate-400 mt-2">
            REST API Documentation v1.0.0 • FastAPI 0.115.3
          </p>
        </div>
        <>
          <button className="btn btn-primary" onClick={openAuth}>
            {authorized ? (
              <Check className="w-4 h-4 text-green-300" />
            ) : (
              <Lock className="w-4 h-4" />
            )}
            <span className="ml-2">{authorized ? 'Authorized' : 'Authorize'}</span>
          </button>

          {showAuth && (
            <div className="fixed inset-0 z-50 flex items-center justify-center">
              <div className="absolute inset-0 bg-black/60" onClick={closeAuth} />
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 w-full max-w-lg z-10">
                <h3 className="text-lg font-semibold text-slate-100 mb-3">Authorize</h3>
                <p className="text-sm text-slate-400 mb-3">Enter your Bearer token (JWT) to authorize requests from the UI.</p>
                <input
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Bearer eyJhbGci..."
                  className="w-full bg-slate-950/60 border border-slate-800 rounded px-3 py-2 text-sm text-slate-200 mb-4"
                />
                <div className="flex gap-2 justify-end">
                  <button className="btn btn-secondary" onClick={clearAuth}>Clear</button>
                  <button className="btn" onClick={closeAuth}>Cancel</button>
                  <button className="btn btn-primary" onClick={saveAuth}>Save</button>
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
            <h3 className="font-semibold text-slate-200 mb-1">Base URL</h3>
            <code className="text-sm text-sky-400 bg-slate-950/60 px-3 py-1 rounded">
              http://localhost:8000
            </code>
            <p className="text-sm text-slate-400 mt-2">
              All authenticated endpoints require a Bearer token in the Authorization header:
            </p>
            <code className="text-xs text-slate-300 bg-slate-950/60 px-3 py-1 rounded mt-2 inline-block">
              Authorization: Bearer {"<"}access_token{">"}
            </code>
          </div>
        </div>
      </div>

      {/* Section Filter */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedSection(null)}
          className={`btn ${!selectedSection ? 'btn-primary' : 'btn-secondary'}`}
        >
          All Endpoints
        </button>
        {apiSections.map((section) => (
          <button
            key={section.title}
            onClick={() => setSelectedSection(section.title)}
            className={`btn ${selectedSection === section.title ? 'btn-primary' : 'btn-secondary'}`}
          >
            {section.icon}
            {section.title}
          </button>
        ))}
      </div>

      {/* API Sections */}
      {filteredSections.map((section) => (
        <div key={section.title}>
          <div className="flex items-center gap-3 mb-4">
            <div className="glow-ring p-2">
              {section.icon}
            </div>
            <h2 className="text-2xl font-bold text-slate-100">{section.title}</h2>
          </div>
          <div className="space-y-3">
            {section.endpoints.map((endpoint, idx) => (
              <EndpointCard key={idx} endpoint={endpoint} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

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
  Check,
  Zap,
  Settings,
  BookOpen,
  RefreshCw
} from 'lucide-react';
import toast from 'react-hot-toast';
import { buildApiUrl } from '../lib/api';

// ==================== Types ====================

interface User {
  id: string;
  username: string;
  role: string;
}

interface ApiEndpoint {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  path: string;
  description: string;
  requiresAuth?: boolean;
  params?: { name: string; type: string; required: boolean; description: string }[];
  body?: { field: string; type: string; required: boolean; description: string }[];
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

const apiSections: ApiSection[] = [
  {
    title: 'Authentication',
    icon: <Lock className="w-5 h-5" />,
    endpoints: [
      {
        method: 'POST',
        path: '/api/auth/login',
        description: 'Authenticate user and get JWT token',
        rateLimit: 'auth_login',
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'password', type: 'string', required: true, description: 'Password' }
        ],
        response: `{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": { "id": 1, "username": "admin", "role": "admin" }
}`
      },
      {
        method: 'POST',
        path: '/api/auth/register',
        description: 'Register new user account',
        rateLimit: 'auth_register',
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'email', type: 'string', required: true, description: 'Email address' },
          { field: 'password', type: 'string', required: true, description: 'Password' }
        ],
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
        description: 'Get current authenticated user',
        requiresAuth: true,
        response: `{
  "user": { "id": 1, "username": "admin", "role": "admin" }
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
        description: 'List files in directory',
        requiresAuth: true,
        rateLimit: 'file_list',
        params: [
          { name: 'path', type: 'string', required: false, description: 'Directory path' }
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
        description: 'Upload file',
        requiresAuth: true,
        rateLimit: 'file_upload',
        body: [
          { field: 'file', type: 'file', required: true, description: 'File to upload' },
          { field: 'path', type: 'string', required: false, description: 'Target directory' }
        ],
        response: `{ "filename": "uploaded.txt", "path": "/uploaded.txt", "size": 2048 }`
      },
      {
        method: 'GET',
        path: '/api/files/download/{path}',
        description: 'Download file',
        requiresAuth: true,
        rateLimit: 'file_download',
        params: [
          { name: 'path', type: 'string', required: true, description: 'File path' }
        ],
        response: 'Binary file content'
      },
      {
        method: 'DELETE',
        path: '/api/files/{path}',
        description: 'Delete file or folder',
        requiresAuth: true,
        rateLimit: 'file_delete',
        params: [
          { name: 'path', type: 'string', required: true, description: 'Path to delete' }
        ],
        response: `{ "message": "Path deleted successfully" }`
      }
    ]
  },
  {
    title: 'Shares',
    icon: <Shield className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/shares',
        description: 'List all shares',
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
        description: 'Create new share link',
        requiresAuth: true,
        rateLimit: 'share_create',
        body: [
          { field: 'path', type: 'string', required: true, description: 'Path to share' },
          { field: 'expires_in_hours', type: 'number', required: false, description: 'Expiration hours' }
        ],
        response: `{ "token": "abc123", "url": "/share/abc123" }`
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
        description: 'Get system information',
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
        description: 'Get live system telemetry',
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
    title: 'Logging',
    icon: <Terminal className="w-5 h-5" />,
    endpoints: [
      {
        method: 'GET',
        path: '/api/logging/disk-io',
        description: 'Get disk I/O logs',
        requiresAuth: true,
        response: `{
  "logs": [{ "timestamp": "...", "operation": "read", "bytes": 4096 }]
}`
      },
      {
        method: 'GET',
        path: '/api/logging/file-access',
        description: 'Get file access logs',
        requiresAuth: true,
        response: `{
  "logs": [{ "timestamp": "...", "user": "admin", "action": "download" }]
}`
      }
    ]
  }
];

// ==================== Method Colors ====================

const methodColors: Record<string, string> = {
  GET: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  POST: 'bg-green-500/20 text-green-400 border-green-500/30',
  PUT: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  DELETE: 'bg-red-500/20 text-red-400 border-red-500/30'
};

// ==================== Endpoint Card Component ====================

interface EndpointCardProps {
  endpoint: ApiEndpoint;
  rateLimits: Record<string, RateLimitConfig>;
  isAdmin: boolean;
  onEditRateLimit?: (config: RateLimitConfig) => void;
}

function EndpointCard({ endpoint, rateLimits, isAdmin, onEditRateLimit }: EndpointCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const rateLimit = endpoint.rateLimit ? rateLimits[endpoint.rateLimit] : null;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 p-4 hover:border-white/20 transition-all">
      <div 
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-3 flex-1 flex-wrap">
          <span className={`px-3 py-1 rounded-lg text-xs font-bold border ${methodColors[endpoint.method]}`}>
            {endpoint.method}
          </span>
          <code className="text-cyan-400 font-mono text-sm">{endpoint.path}</code>
          <span className="text-gray-400 text-sm hidden md:inline">{endpoint.description}</span>
          {endpoint.requiresAuth && (
            <span title="Requires authentication"><Shield className="w-4 h-4 text-amber-400" /></span>
          )}
          {rateLimit && (
            <span 
              className={`px-2 py-0.5 rounded text-xs font-mono ${
                rateLimit.enabled 
                  ? 'bg-green-500/20 text-green-400' 
                  : 'bg-gray-500/20 text-gray-500'
              }`}
              title={`Rate limit: ${rateLimit.limit_string}`}
            >
              <Zap className="w-3 h-3 inline mr-1" />
              {rateLimit.limit_string}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && rateLimit && onEditRateLimit && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEditRateLimit(rateLimit);
              }}
              className="p-1.5 rounded-lg bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors"
              title="Edit rate limit"
            >
              <Settings className="w-4 h-4" />
            </button>
          )}
          {isOpen ? (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </div>

      {isOpen && (
        <div className="mt-4 space-y-4 border-t border-white/10 pt-4">
          <p className="text-gray-300 text-sm md:hidden">{endpoint.description}</p>
          
          {endpoint.params && endpoint.params.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-300 mb-2">Parameters</h4>
              <div className="space-y-2">
                {endpoint.params.map((param, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-sm flex-wrap">
                    <code className="text-cyan-400 font-mono">{param.name}</code>
                    <span className="text-gray-500">({param.type})</span>
                    {param.required && <span className="text-red-400 text-xs">required</span>}
                    <span className="text-gray-400">{param.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.body && endpoint.body.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-300 mb-2">Request Body</h4>
              <div className="space-y-2">
                {endpoint.body.map((field, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-sm flex-wrap">
                    <code className="text-violet-400 font-mono">{field.field}</code>
                    <span className="text-gray-500">({field.type})</span>
                    {field.required && <span className="text-red-400 text-xs">required</span>}
                    <span className="text-gray-400">{field.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.response && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-gray-300">Response</h4>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(endpoint.response!);
                  }}
                  className="text-gray-400 hover:text-cyan-400 transition-colors p-1"
                >
                  {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              <pre className="bg-black/30 border border-white/10 rounded-lg p-3 text-xs overflow-x-auto">
                <code className="text-gray-300">{endpoint.response}</code>
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
}

function RateLimitModal({ config, onClose, onSave }: RateLimitModalProps) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-900 border border-white/10 rounded-xl p-6 w-full max-w-md shadow-2xl">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5 text-yellow-400" />
          Edit Rate Limit
        </h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Endpoint</label>
            <code className="block w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg text-cyan-400">
              {config.endpoint_type}
            </code>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Rate Limit</label>
            <input
              type="text"
              value={form.limit_string}
              onChange={(e) => setForm({ ...form, limit_string: e.target.value })}
              className="w-full px-3 py-2 bg-black/30 border border-white/20 rounded-lg text-white focus:border-cyan-500 focus:outline-none"
              placeholder="5/minute"
            />
            <p className="text-xs text-gray-500 mt-1">Format: number/unit (e.g., 5/minute, 100/hour)</p>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 bg-black/30 border border-white/20 rounded-lg text-white focus:border-cyan-500 focus:outline-none"
              placeholder="Rate limit description"
            />
          </div>
          
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="enabled"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="w-4 h-4 rounded"
            />
            <label htmlFor="enabled" className="text-sm text-gray-300">Enabled</label>
          </div>
        </div>
        
        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export default function ApiCenterPage() {
  const [user, setUser] = useState<User | null>(null);
  const [activeTab, setActiveTab] = useState<'docs' | 'limits'>('docs');
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [rateLimits, setRateLimits] = useState<Record<string, RateLimitConfig>>({});
  const [rateLimitsList, setRateLimitsList] = useState<RateLimitConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingConfig, setEditingConfig] = useState<RateLimitConfig | null>(null);

  const isAdmin = user?.role === 'admin';

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
      toast.error('Not authenticated');
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
      toast.success('Rate limit updated');
      loadRateLimits();
    } else {
      const error = await response.json();
      toast.error(error.detail || 'Failed to update rate limit');
      throw new Error('Failed to save');
    }
  };

  const handleSeedDefaults = async () => {
    if (!confirm('This will seed default rate limit configurations. Continue?')) return;

    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits/seed-defaults'), {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        toast.success('Default rate limits seeded');
        loadRateLimits();
      } else {
        toast.error('Failed to seed defaults');
      }
    } catch (error) {
      toast.error('Failed to seed defaults');
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
        toast.success(`Rate limit ${!config.enabled ? 'enabled' : 'disabled'}`);
        loadRateLimits();
      }
    } catch (error) {
      toast.error('Failed to toggle rate limit');
    }
  };

  const filteredSections = selectedSection
    ? apiSections.filter(s => s.title === selectedSection)
    : apiSections;

  const getCategoryFromEndpoint = (endpoint: string): string => {
    if (endpoint.startsWith('auth_')) return 'Authentication';
    if (endpoint.startsWith('file_')) return 'File Operations';
    if (endpoint.startsWith('share_')) return 'Sharing';
    if (endpoint.startsWith('mobile_')) return 'Mobile';
    if (endpoint.startsWith('vpn_')) return 'VPN';
    if (endpoint.includes('admin')) return 'Admin';
    if (endpoint.includes('user')) return 'Users';
    if (endpoint.includes('system')) return 'System';
    return 'Other';
  };

  const groupedRateLimits = rateLimitsList.reduce((acc, config) => {
    const category = getCategoryFromEndpoint(config.endpoint_type);
    if (!acc[category]) acc[category] = [];
    acc[category].push(config);
    return acc;
  }, {} as Record<string, RateLimitConfig[]>);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent flex items-center gap-3">
            <Code className="w-8 h-8 text-cyan-400" />
            API Center
          </h1>
          <p className="text-gray-400 mt-1">
            REST API Documentation {isAdmin && '& Rate Limit Configuration'}
          </p>
        </div>
        
        {/* Tab Buttons */}
        {isAdmin && (
          <div className="flex gap-2 bg-white/5 p-1 rounded-lg">
            <button
              onClick={() => setActiveTab('docs')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                activeTab === 'docs' 
                  ? 'bg-cyan-600 text-white' 
                  : 'text-gray-400 hover:text-white hover:bg-white/10'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              API Docs
            </button>
            <button
              onClick={() => setActiveTab('limits')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                activeTab === 'limits' 
                  ? 'bg-yellow-600 text-white' 
                  : 'text-gray-400 hover:text-white hover:bg-white/10'
              }`}
            >
              <Zap className="w-4 h-4" />
              Rate Limits
            </button>
          </div>
        )}
      </div>

      {/* API Docs Tab */}
      {activeTab === 'docs' && (
        <>
          {/* Base URL Info */}
          <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <Code className="w-5 h-5 text-cyan-400 mt-0.5" />
              <div>
                <h3 className="font-semibold text-white mb-1">Base URL</h3>
                <code className="text-sm text-cyan-400 bg-black/30 px-3 py-1 rounded">
                  http://localhost:8000
                </code>
                <p className="text-sm text-gray-400 mt-2">
                  All authenticated endpoints require: 
                  <code className="text-xs text-gray-300 bg-black/30 px-2 py-0.5 rounded ml-2">
                    Authorization: Bearer {"<token>"}
                  </code>
                </p>
              </div>
            </div>
          </div>

          {/* Section Filter */}
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setSelectedSection(null)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                !selectedSection 
                  ? 'bg-cyan-600 text-white' 
                  : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
              }`}
            >
              All
            </button>
            {apiSections.map((section) => (
              <button
                key={section.title}
                onClick={() => setSelectedSection(section.title)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                  selectedSection === section.title 
                    ? 'bg-cyan-600 text-white' 
                    : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
                }`}
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
                <div className="p-2 bg-cyan-500/20 rounded-lg text-cyan-400">
                  {section.icon}
                </div>
                <h2 className="text-xl font-bold text-white">{section.title}</h2>
              </div>
              <div className="space-y-3">
                {section.endpoints.map((endpoint, idx) => (
                  <EndpointCard 
                    key={idx} 
                    endpoint={endpoint} 
                    rateLimits={rateLimits}
                    isAdmin={isAdmin}
                    onEditRateLimit={setEditingConfig}
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
          <div className="flex gap-3">
            <button
              onClick={handleSeedDefaults}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors flex items-center gap-2"
            >
              🌱 Seed Defaults
            </button>
            <button
              onClick={loadRateLimits}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>

          {/* Info Box */}
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
            <h3 className="text-yellow-400 font-semibold mb-2 flex items-center gap-2">
              <Zap className="w-5 h-5" />
              Rate Limit Protection
            </h3>
            <p className="text-gray-300 text-sm">
              Rate limits protect your API from abuse. Format: <code className="bg-black/30 px-2 py-1 rounded">number/unit</code> 
              {' '}(e.g., <code className="bg-black/30 px-2 py-1 rounded">5/minute</code>, <code className="bg-black/30 px-2 py-1 rounded">100/hour</code>)
            </p>
          </div>

          {/* Rate Limits by Category */}
          {loading ? (
            <div className="text-gray-400">Loading rate limits...</div>
          ) : Object.keys(groupedRateLimits).length === 0 ? (
            <div className="bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 p-12 text-center">
              <p className="text-gray-400 mb-4">No rate limit configurations found</p>
              <button
                onClick={handleSeedDefaults}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
              >
                🌱 Seed Default Configurations
              </button>
            </div>
          ) : (
            Object.entries(groupedRateLimits).map(([category, configs]) => (
              <div key={category}>
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-yellow-500/20 rounded-lg text-yellow-400">
                    <Zap className="w-5 h-5" />
                  </div>
                  <h2 className="text-xl font-bold text-white">{category}</h2>
                </div>
                <div className="space-y-3">
                  {configs.map((config) => (
                    <div 
                      key={config.id} 
                      className="bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 p-4 hover:border-white/20 transition-all"
                    >
                      <div className="flex items-center justify-between gap-4 flex-wrap">
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          <code className="text-cyan-400 font-mono text-sm">{config.endpoint_type}</code>
                          <span className="text-green-400 font-semibold text-lg">{config.limit_string}</span>
                          <button
                            onClick={() => handleToggleEnabled(config)}
                            className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors ${
                              config.enabled
                                ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                                : 'bg-gray-500/20 text-gray-400 hover:bg-gray-500/30'
                            }`}
                          >
                            {config.enabled ? '✓ Enabled' : '✗ Disabled'}
                          </button>
                        </div>
                        <button
                          onClick={() => setEditingConfig(config)}
                          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors flex items-center gap-2"
                        >
                          <Settings className="w-4 h-4" />
                          Edit
                        </button>
                      </div>
                      {config.description && (
                        <p className="text-gray-400 text-sm mt-2">{config.description}</p>
                      )}
                    </div>
                  ))}
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
        />
      )}
    </div>
  );
}

import {
  Download,
  Upload,
  Trash2,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Search,
  Filter,
  FileDown,
  Calendar,
  RefreshCw,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';

interface ActivityLogEntry {
  id: number;
  timestamp: string;
  activityType: 'upload' | 'download' | 'delete' | 'conflict' | 'error';
  filePath: string;
  folderId: string;
  details: string;
  fileSize: number;
  status: 'success' | 'failed' | 'pending';
}

interface ActivityLogProps {
  onClose?: () => void;
}

type FilterType = 'all' | 'upload' | 'download' | 'delete' | 'conflict' | 'error';
type ExportFormat = 'csv' | 'json';

/**
 * ActivityLog - Display sync activity history with filtering and export
 */
export default function ActivityLog({ onClose }: ActivityLogProps) {
  const [activities, setActivities] = useState<ActivityLogEntry[]>([]);
  const [filteredActivities, setFilteredActivities] = useState<ActivityLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  useEffect(() => {
    loadActivities();
  }, []);

  useEffect(() => {
    applyFilters();
  }, [activities, searchQuery, filterType, startDate, endDate]);

  const loadActivities = async () => {
    setLoading(true);
    try {
      const response = await (window as any).electronAPI?.sendBackendCommand?.({
        type: 'get_activity_logs',
        data: { limit: 1000 },
      });

      if (response?.success && response?.data?.logs) {
        setActivities(response.data.logs);
      } else {
        // Mock data for development
        setActivities(generateMockData());
      }
    } catch (error) {
      toast.error('Failed to load activity logs');
      setActivities(generateMockData());
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...activities];

    // Filter by type
    if (filterType !== 'all') {
      filtered = filtered.filter((log) => log.activityType === filterType);
    }

    // Filter by search query (filename)
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((log) =>
        log.filePath.toLowerCase().includes(query)
      );
    }

    // Filter by date range
    if (startDate) {
      filtered = filtered.filter((log) => log.timestamp >= startDate);
    }

    if (endDate) {
      filtered = filtered.filter((log) => log.timestamp <= endDate);
    }

    setFilteredActivities(filtered);
  };

  const exportLogs = (format: ExportFormat) => {
    try {
      if (format === 'csv') {
        exportAsCSV();
      } else {
        exportAsJSON();
      }
      toast.success(`Exported ${filteredActivities.length} activities as ${format.toUpperCase()}`);
    } catch (error) {
      toast.error('Failed to export logs');
    }
  };

  const exportAsCSV = () => {
    const headers = ['Timestamp', 'Type', 'File Path', 'Size (bytes)', 'Status', 'Details'];
    const rows = filteredActivities.map((log) => [
      log.timestamp,
      log.activityType,
      log.filePath,
      log.fileSize.toString(),
      log.status,
      log.details || '',
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.map((cell) => `"${cell}"`).join(',')),
    ].join('\n');

    downloadFile(csvContent, 'activity-log.csv', 'text/csv');
  };

  const exportAsJSON = () => {
    const jsonContent = JSON.stringify(filteredActivities, null, 2);
    downloadFile(jsonContent, 'activity-log.json', 'application/json');
  };

  const downloadFile = (content: string, filename: string, mimeType: string) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'upload':
        return <Upload className="h-5 w-5 text-blue-500" />;
      case 'download':
        return <Download className="h-5 w-5 text-green-500" />;
      case 'delete':
        return <Trash2 className="h-5 w-5 text-red-500" />;
      case 'conflict':
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case 'error':
        return <XCircle className="h-5 w-5 text-red-600" />;
      default:
        return <CheckCircle className="h-5 w-5 text-gray-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const colors = {
      success: 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200',
      failed: 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200',
      pending: 'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-200',
    };

    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${colors[status as keyof typeof colors] || colors.pending}`}>
        {status}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin mb-4">
            <RefreshCw className="h-8 w-8 text-blue-500" />
          </div>
          <p className="text-gray-600 dark:text-gray-400">Loading activity log...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileDown className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Activity Log</h1>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            >
              ✕
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
          {filteredActivities.length} activities {filterType !== 'all' && `(${filterType})`}
        </p>
      </div>

      {/* Filters */}
      <div className="border-b border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800 space-y-4">
        {/* Search */}
        <div className="flex items-center gap-2">
          <Search className="h-5 w-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search by filename..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 px-4 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Filters Row */}
        <div className="flex flex-wrap gap-3">
          {/* Type Filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-gray-400" />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value as FilterType)}
              className="px-4 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Types</option>
              <option value="upload">Upload</option>
              <option value="download">Download</option>
              <option value="delete">Delete</option>
              <option value="conflict">Conflict</option>
              <option value="error">Error</option>
            </select>
          </div>

          {/* Date Range */}
          <div className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-gray-400" />
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-4 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
              placeholder="Start date"
            />
            <span className="text-gray-400">to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-4 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
              placeholder="End date"
            />
          </div>

          {/* Export Buttons */}
          <div className="ml-auto flex gap-2">
            <button
              onClick={() => exportLogs('csv')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition flex items-center gap-2"
            >
              <FileDown className="h-4 w-4" />
              Export CSV
            </button>
            <button
              onClick={() => exportLogs('json')}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition flex items-center gap-2"
            >
              <FileDown className="h-4 w-4" />
              Export JSON
            </button>
            <button
              onClick={loadActivities}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Activity List */}
      <div className="flex-1 overflow-y-auto">
        {filteredActivities.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-500 dark:text-gray-400">
              <FileDown className="h-16 w-16 mx-auto mb-4 opacity-20" />
              <p className="text-lg font-medium">No activities found</p>
              <p className="text-sm">Try adjusting your filters</p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {filteredActivities.map((log) => (
              <div
                key={log.id}
                className="p-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
              >
                <div className="flex items-start gap-4">
                  <div className="mt-1">{getActivityIcon(log.activityType)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="font-medium text-gray-900 dark:text-white truncate">
                        {log.filePath}
                      </h3>
                      {getStatusBadge(log.status)}
                    </div>
                    <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                      <span>{formatTimestamp(log.timestamp)}</span>
                      <span className="capitalize">{log.activityType}</span>
                      {log.fileSize > 0 && <span>{formatFileSize(log.fileSize)}</span>}
                    </div>
                    {log.details && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                        {log.details}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Generate mock data for development
function generateMockData(): ActivityLogEntry[] {
  const types: ActivityLogEntry['activityType'][] = ['upload', 'download', 'delete', 'conflict', 'error'];
  const statuses: ActivityLogEntry['status'][] = ['success', 'failed', 'pending'];
  const files = [
    'Documents/report.pdf',
    'Photos/vacation.jpg',
    'Projects/website/index.html',
    'Music/playlist.mp3',
    'Videos/tutorial.mp4',
  ];

  const data: ActivityLogEntry[] = [];
  const now = new Date();

  for (let i = 0; i < 50; i++) {
    const timestamp = new Date(now.getTime() - Math.random() * 7 * 24 * 60 * 60 * 1000);
    const type = types[Math.floor(Math.random() * types.length)];
    const status = type === 'error' ? 'failed' : statuses[Math.floor(Math.random() * statuses.length)];

    data.push({
      id: i + 1,
      timestamp: timestamp.toISOString(),
      activityType: type,
      filePath: files[Math.floor(Math.random() * files.length)],
      folderId: 'folder-1',
      details: type === 'conflict' ? 'File modified on both local and remote' : type === 'error' ? 'Network timeout' : '',
      fileSize: Math.floor(Math.random() * 10000000),
      status,
    });
  }

  return data.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

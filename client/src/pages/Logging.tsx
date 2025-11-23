import React, { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { loggingApi } from '../api/logging';
import type { DiskIOData, FileAccessLogsResponse } from '../api/logging';

const Logging: React.FC = () => {
  const [diskIOData, setDiskIOData] = useState<DiskIOData | null>(null);
  const [fileAccessLogs, setFileAccessLogs] = useState<FileAccessLogsResponse | null>(
    null
  );
  const [selectedDisk, setSelectedDisk] = useState<string>('');
  const [timeRange, setTimeRange] = useState<number>(24);
  const [actionFilter, setActionFilter] = useState<string>('');
  const [userFilter, setUserFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [timeRange, actionFilter, userFilter]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [diskData, logsData] = await Promise.all([
        loggingApi.getDiskIOLogs(timeRange),
        loggingApi.getFileAccessLogs({
          limit: 100,
          days: Math.ceil(timeRange / 24),
          action: actionFilter || undefined,
          user: userFilter || undefined,
        }),
      ]);

      setDiskIOData(diskData);
      setFileAccessLogs(logsData);

      // Select first disk if none selected
      if (!selectedDisk && Object.keys(diskData.disks).length > 0) {
        setSelectedDisk(Object.keys(diskData.disks)[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load logging data');
      console.error('Error loading logging data:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number | undefined): string => {
    if (!bytes) return '-';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    return `${size.toFixed(2)} ${units[unitIndex]}`;
  };

  const formatTimestamp = (timestamp: string): string => {
    return new Date(timestamp).toLocaleString();
  };

  const formatChartTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    
    // For time ranges > 72 hours (3 days), show only date
    if (timeRange > 72) {
      const month = (date.getMonth() + 1).toString().padStart(2, '0');
      const day = date.getDate().toString().padStart(2, '0');
      return `${day}.${month}`;
    }
    
    // For time ranges > 24 hours but <= 72 hours, show date + time
    if (timeRange > 24) {
      const month = (date.getMonth() + 1).toString().padStart(2, '0');
      const day = date.getDate().toString().padStart(2, '0');
      const hours = date.getHours().toString().padStart(2, '0');
      return `${day}.${month} ${hours}h`;
    }
    
    // For time ranges <= 24 hours, show only time
    return `${date.getHours().toString().padStart(2, '0')}:${date
      .getMinutes()
      .toString()
      .padStart(2, '0')}`;
  };
  
  const formatTooltipTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${day}.${month}.${date.getFullYear()} ${hours}:${minutes}`;
  };

  // Prepare chart data for selected disk
  const getChartData = () => {
    if (!diskIOData || !selectedDisk) return [];

    const samples = diskIOData.disks[selectedDisk] || [];

    // Sample data for display (show every Nth point based on time range)
    const sampleRate = Math.max(1, Math.floor(samples.length / 100));

    return samples
      .filter((_, index) => index % sampleRate === 0)
      .map((sample) => ({
        time: formatChartTimestamp(sample.timestamp),
        timestamp: sample.timestamp,
        Read: sample.readMbps,
        Write: sample.writeMbps,
      }));
  };

  const getIOPSChartData = () => {
    if (!diskIOData || !selectedDisk) return [];

    const samples = diskIOData.disks[selectedDisk] || [];
    const sampleRate = Math.max(1, Math.floor(samples.length / 100));

    return samples
      .filter((_, index) => index % sampleRate === 0)
      .map((sample) => ({
        time: formatChartTimestamp(sample.timestamp),
        timestamp: sample.timestamp,
        'Read IOPS': sample.readIops,
        'Write IOPS': sample.writeIops,
      }));
  };

  const availableActions = Array.from(
    new Set(fileAccessLogs?.logs.map((log) => log.action) || [])
  ).sort();

  const availableUsers = Array.from(
    new Set(fileAccessLogs?.logs.map((log) => log.user) || [])
  ).sort();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading logging data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded">
        <p className="font-bold">Error</p>
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Logging</h1>
          <p className="text-gray-400 mt-1">
            System activity logs and disk I/O monitoring
            {diskIOData?.dev_mode && (
              <span className="ml-2 text-yellow-400 text-sm">
                (Dev Mode - Mock Data)
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="bg-gray-700 text-white px-4 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
          >
            <option value={1}>Last 1 hour</option>
            <option value={6}>Last 6 hours</option>
            <option value={24}>Last 24 hours</option>
            <option value={72}>Last 3 days</option>
            <option value={168}>Last week</option>
          </select>
          <button
            onClick={loadData}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Disk I/O Charts */}
      <div className="bg-gray-800 rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-white">Disk I/O Activity</h2>
          {diskIOData && Object.keys(diskIOData.disks).length > 1 && (
            <select
              value={selectedDisk}
              onChange={(e) => setSelectedDisk(e.target.value)}
              className="bg-gray-700 text-white px-4 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
            >
              {Object.keys(diskIOData.disks).map((disk) => (
                <option key={disk} value={disk}>
                  {disk}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Throughput Chart */}
        <div className="mb-8">
          <h3 className="text-lg font-medium text-gray-300 mb-3">
            Disk Throughput (MB/s)
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart 
              data={getChartData()}
              margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="time" 
                stroke="#9CA3AF"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                stroke="#9CA3AF"
                label={{ value: 'MB/s', angle: -90, position: 'insideLeft', style: { fill: '#9CA3AF' } }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '0.375rem',
                }}
                labelStyle={{ color: '#F3F4F6' }}
                labelFormatter={(value, payload) => {
                  if (payload && payload.length > 0) {
                    return formatTooltipTimestamp(payload[0].payload.timestamp);
                  }
                  return value;
                }}
                formatter={(value: number) => [`${value} MB/s`, '']}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="Read"
                stroke="#3B82F6"
                strokeWidth={2}
                dot={false}
                name="Read"
              />
              <Line
                type="monotone"
                dataKey="Write"
                stroke="#10B981"
                strokeWidth={2}
                dot={false}
                name="Write"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* IOPS Chart */}
        <div>
          <h3 className="text-lg font-medium text-gray-300 mb-3">
            Disk Operations (IOPS)
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart 
              data={getIOPSChartData()}
              margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="time" 
                stroke="#9CA3AF"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                stroke="#9CA3AF"
                label={{ value: 'IOPS', angle: -90, position: 'insideLeft', style: { fill: '#9CA3AF' } }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '0.375rem',
                }}
                labelStyle={{ color: '#F3F4F6' }}
                labelFormatter={(value, payload) => {
                  if (payload && payload.length > 0) {
                    return formatTooltipTimestamp(payload[0].payload.timestamp);
                  }
                  return value;
                }}
                formatter={(value: number) => [`${value} IOPS`, '']}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="Read IOPS"
                stroke="#8B5CF6"
                strokeWidth={2}
                dot={false}
                name="Read IOPS"
              />
              <Line
                type="monotone"
                dataKey="Write IOPS"
                stroke="#F59E0B"
                strokeWidth={2}
                dot={false}
                name="Write IOPS"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* File Access Logs */}
      <div className="bg-gray-800 rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-white">File Access Logs</h2>
          <div className="flex gap-2">
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="bg-gray-700 text-white px-3 py-1 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm"
            >
              <option value="">All Actions</option>
              {availableActions.map((action) => (
                <option key={action} value={action}>
                  {action}
                </option>
              ))}
            </select>
            <select
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              className="bg-gray-700 text-white px-3 py-1 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm"
            >
              <option value="">All Users</option>
              {availableUsers.map((user) => (
                <option key={user} value={user}>
                  {user}
                </option>
              ))}
            </select>
          </div>
        </div>

        {fileAccessLogs && fileAccessLogs.logs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-700">
              <thead>
                <tr className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">User</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">File</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Duration</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {fileAccessLogs.logs.map((log, index) => (
                  <tr
                    key={index}
                    className="text-sm text-gray-300 hover:bg-gray-700/50"
                  >
                    <td className="px-4 py-3 whitespace-nowrap">
                      {formatTimestamp(log.timestamp)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-900/50 text-blue-300">
                        {log.user}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                          log.action === 'read' || log.action === 'download'
                            ? 'bg-green-900/50 text-green-300'
                            : log.action === 'write' ||
                              log.action === 'upload' ||
                              log.action === 'create'
                            ? 'bg-yellow-900/50 text-yellow-300'
                            : log.action === 'delete'
                            ? 'bg-red-900/50 text-red-300'
                            : 'bg-gray-700 text-gray-300'
                        }`}
                      >
                        {log.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate" title={log.resource}>
                      {log.resource}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {formatBytes(log.details?.size_bytes)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {log.details?.duration_ms
                        ? `${log.details.duration_ms}ms`
                        : '-'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {log.success ? (
                        <span className="inline-flex items-center text-green-400">
                          <svg
                            className="w-4 h-4 mr-1"
                            fill="currentColor"
                            viewBox="0 0 20 20"
                          >
                            <path
                              fillRule="evenodd"
                              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                              clipRule="evenodd"
                            />
                          </svg>
                          Success
                        </span>
                      ) : (
                        <span
                          className="inline-flex items-center text-red-400"
                          title={log.error}
                        >
                          <svg
                            className="w-4 h-4 mr-1"
                            fill="currentColor"
                            viewBox="0 0 20 20"
                          >
                            <path
                              fillRule="evenodd"
                              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                              clipRule="evenodd"
                            />
                          </svg>
                          Failed
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">No file access logs found</div>
        )}

        {fileAccessLogs && fileAccessLogs.total > fileAccessLogs.logs.length && (
          <div className="mt-4 text-center text-sm text-gray-400">
            Showing {fileAccessLogs.logs.length} of {fileAccessLogs.total} logs
          </div>
        )}
      </div>
    </div>
  );
};

export default Logging;

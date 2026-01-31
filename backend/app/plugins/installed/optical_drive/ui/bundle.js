/**
 * Optical Drive Plugin UI Bundle
 *
 * React components for optical drive management including:
 * - Drive list with status indicators
 * - Job progress tracking
 * - Path selection dialogs
 * - Burn/rip controls
 */

// Since this is loaded dynamically, we use the global React from the parent app
const React = window.React;
const { useState, useEffect, useCallback } = React;

// Plugin registration
const PLUGIN_NAME = 'optical_drive';

  // API helper
  const api = {
    baseUrl: `/api/plugins/${PLUGIN_NAME}`,

    async fetch(endpoint, options = {}) {
      const token = localStorage.getItem('token');
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          ...options.headers,
        },
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
      }
      return response.json();
    },

    getDrives() {
      return this.fetch('/drives');
    },

    getDriveInfo(device) {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/info`);
    },

    eject(device) {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/eject`, { method: 'POST' });
    },

    closeTray(device) {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/close`, { method: 'POST' });
    },

    readIso(device, outputPath) {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/read/iso`, {
        method: 'POST',
        body: JSON.stringify({ output_path: outputPath }),
      });
    },

    ripAudio(device, outputDir) {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/read/audio`, {
        method: 'POST',
        body: JSON.stringify({ output_dir: outputDir }),
      });
    },

    burnIso(device, isoPath, speed = 0) {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/burn/iso`, {
        method: 'POST',
        body: JSON.stringify({ iso_path: isoPath, speed }),
      });
    },

    burnAudio(device, wavFiles, speed = 0) {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/burn/audio`, {
        method: 'POST',
        body: JSON.stringify({ wav_files: wavFiles, speed }),
      });
    },

    blankDisc(device, mode = 'fast') {
      const devicePath = device.replace('/dev/', '');
      return this.fetch(`/drives/${devicePath}/blank`, {
        method: 'POST',
        body: JSON.stringify({ mode }),
      });
    },

    getJobs() {
      return this.fetch('/jobs');
    },

    getJob(jobId) {
      return this.fetch(`/jobs/${jobId}`);
    },

    cancelJob(jobId) {
      return this.fetch(`/jobs/${jobId}/cancel`, { method: 'POST' });
    },
  };

  // Icons (using Lucide SVG paths)
  const Icons = {
    Disc: () => React.createElement('svg', {
      className: 'w-5 h-5',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('circle', { cx: 12, cy: 12, r: 10 }),
      React.createElement('circle', { cx: 12, cy: 12, r: 3 })
    ),

    Eject: () => React.createElement('svg', {
      className: 'w-4 h-4',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('polygon', { points: '12 2 2 12 22 12' }),
      React.createElement('rect', { x: 2, y: 16, width: 20, height: 4 })
    ),

    Play: () => React.createElement('svg', {
      className: 'w-4 h-4',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('polygon', { points: '5 3 19 12 5 21 5 3' })
    ),

    Download: () => React.createElement('svg', {
      className: 'w-4 h-4',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('path', { d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' }),
      React.createElement('polyline', { points: '7 10 12 15 17 10' }),
      React.createElement('line', { x1: 12, y1: 15, x2: 12, y2: 3 })
    ),

    Flame: () => React.createElement('svg', {
      className: 'w-4 h-4',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('path', { d: 'M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z' })
    ),

    X: () => React.createElement('svg', {
      className: 'w-4 h-4',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('line', { x1: 18, y1: 6, x2: 6, y2: 18 }),
      React.createElement('line', { x1: 6, y1: 6, x2: 18, y2: 18 })
    ),

    Music: () => React.createElement('svg', {
      className: 'w-4 h-4',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('path', { d: 'M9 18V5l12-2v13' }),
      React.createElement('circle', { cx: 6, cy: 18, r: 3 }),
      React.createElement('circle', { cx: 18, cy: 16, r: 3 })
    ),

    RefreshCw: () => React.createElement('svg', {
      className: 'w-4 h-4',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('polyline', { points: '23 4 23 10 17 10' }),
      React.createElement('polyline', { points: '1 20 1 14 7 14' }),
      React.createElement('path', { d: 'M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15' })
    ),

    Loader: () => React.createElement('svg', {
      className: 'w-4 h-4 animate-spin',
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2
    },
      React.createElement('circle', { cx: 12, cy: 12, r: 10, opacity: 0.25 }),
      React.createElement('path', { d: 'M12 2a10 10 0 0 1 10 10', opacity: 1 })
    ),
  };

  // Progress Bar Component
  function ProgressBar({ progress, className = '' }) {
    return React.createElement('div', {
      className: `w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 ${className}`
    },
      React.createElement('div', {
        className: 'bg-blue-600 h-2.5 rounded-full transition-all duration-300',
        style: { width: `${Math.min(100, Math.max(0, progress))}%` }
      })
    );
  }

  // Button Component
  function Button({ children, onClick, variant = 'primary', disabled = false, className = '' }) {
    const baseClasses = 'inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

    const variants = {
      primary: 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500',
      secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 focus:ring-gray-500 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600',
      danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
    };

    return React.createElement('button', {
      type: 'button',
      onClick,
      disabled,
      className: `${baseClasses} ${variants[variant]} ${className}`
    }, children);
  }

  // Drive Card Component
  function DriveCard({ drive, onRefresh }) {
    const [isLoading, setIsLoading] = useState(false);
    const [showRipDialog, setShowRipDialog] = useState(false);
    const [showBurnDialog, setShowBurnDialog] = useState(false);

    const handleEject = async () => {
      setIsLoading(true);
      try {
        await api.eject(drive.device);
        onRefresh();
      } catch (error) {
        console.error('Eject failed:', error);
      } finally {
        setIsLoading(false);
      }
    };

    const handleRip = async (outputDir) => {
      setIsLoading(true);
      try {
        if (drive.media_type === 'cd_audio') {
          await api.ripAudio(drive.device, outputDir);
        } else {
          await api.readIso(drive.device, outputDir + '/disc.iso');
        }
        setShowRipDialog(false);
        onRefresh();
      } catch (error) {
        console.error('Rip failed:', error);
      } finally {
        setIsLoading(false);
      }
    };

    const getMediaTypeLabel = (mediaType) => {
      const labels = {
        'cd_audio': 'Audio CD',
        'cd_data': 'Data CD',
        'dvd_data': 'Data DVD',
        'cd_blank': 'Blank CD',
        'dvd_blank': 'Blank DVD',
        'bd_data': 'Blu-ray',
        'bd_blank': 'Blank Blu-ray',
        'none': 'No Disc',
        'unknown': 'Unknown',
      };
      return labels[mediaType] || 'Unknown';
    };

    const getStatusColor = (isReady, isBlank) => {
      if (!isReady) return 'bg-gray-400';
      if (isBlank) return 'bg-yellow-400';
      return 'bg-green-400';
    };

    return React.createElement('div', {
      className: 'bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 border border-gray-200 dark:border-gray-700'
    },
      // Header
      React.createElement('div', { className: 'flex items-center justify-between mb-3' },
        React.createElement('div', { className: 'flex items-center gap-3' },
          React.createElement('div', {
            className: 'p-2 bg-blue-100 dark:bg-blue-900 rounded-lg text-blue-600 dark:text-blue-400'
          }, React.createElement(Icons.Disc)),
          React.createElement('div', null,
            React.createElement('h3', { className: 'font-semibold text-gray-900 dark:text-white' },
              drive.name || drive.device
            ),
            React.createElement('p', { className: 'text-sm text-gray-500 dark:text-gray-400' },
              drive.device
            )
          )
        ),
        React.createElement('span', {
          className: `inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded-full ${
            drive.is_ready ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                          : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
          }`
        },
          React.createElement('span', {
            className: `w-2 h-2 rounded-full ${getStatusColor(drive.is_ready, drive.is_blank)}`
          }),
          drive.is_ready ? getMediaTypeLabel(drive.media_type) : 'No Disc'
        )
      ),

      // Media Details
      drive.is_ready && React.createElement('div', {
        className: 'mb-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-md'
      },
        drive.media_label && React.createElement('p', { className: 'text-sm text-gray-600 dark:text-gray-300' },
          React.createElement('span', { className: 'font-medium' }, 'Label: '),
          drive.media_label
        ),
        drive.total_tracks && React.createElement('p', { className: 'text-sm text-gray-600 dark:text-gray-300' },
          React.createElement('span', { className: 'font-medium' }, 'Tracks: '),
          drive.total_tracks
        ),
        drive.total_size_bytes && React.createElement('p', { className: 'text-sm text-gray-600 dark:text-gray-300' },
          React.createElement('span', { className: 'font-medium' }, 'Size: '),
          formatBytes(drive.total_size_bytes)
        ),
        drive.is_blank && React.createElement('p', { className: 'text-sm text-yellow-600 dark:text-yellow-400' },
          'Ready for burning'
        )
      ),

      // Actions
      React.createElement('div', { className: 'flex flex-wrap gap-2' },
        // Rip/Read button (for discs with content)
        drive.is_ready && !drive.is_blank && React.createElement(Button, {
          onClick: () => setShowRipDialog(true),
          disabled: isLoading,
          variant: 'primary'
        },
          drive.media_type === 'cd_audio'
            ? [React.createElement(Icons.Music, { key: 'icon' }), 'Rip Audio (WAV)']
            : [React.createElement(Icons.Download, { key: 'icon' }), 'Copy to ISO']
        ),

        // Burn button (for blank discs)
        drive.is_blank && drive.can_write && React.createElement(Button, {
          onClick: () => setShowBurnDialog(true),
          disabled: isLoading,
          variant: 'primary'
        },
          React.createElement(Icons.Flame, { key: 'icon' }),
          'Burn Disc'
        ),

        // Eject button
        React.createElement(Button, {
          onClick: handleEject,
          disabled: isLoading,
          variant: 'secondary'
        },
          React.createElement(Icons.Eject, { key: 'icon' }),
          'Eject'
        )
      ),

      // Rip Dialog
      showRipDialog && React.createElement(PathDialog, {
        title: drive.media_type === 'cd_audio' ? 'Rip Audio CD' : 'Copy Disc to ISO',
        onConfirm: handleRip,
        onCancel: () => setShowRipDialog(false),
        isDirectory: drive.media_type === 'cd_audio',
        defaultPath: '/storage/optical'
      }),

      // Burn Dialog
      showBurnDialog && React.createElement(BurnDialog, {
        drive: drive,
        onClose: () => {
          setShowBurnDialog(false);
          onRefresh();
        }
      })
    );
  }

  // Path Selection Dialog
  function PathDialog({ title, onConfirm, onCancel, isDirectory, defaultPath }) {
    const [path, setPath] = useState(defaultPath);

    return React.createElement('div', {
      className: 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50'
    },
      React.createElement('div', {
        className: 'bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-full max-w-md'
      },
        React.createElement('h3', {
          className: 'text-lg font-semibold text-gray-900 dark:text-white mb-4'
        }, title),

        React.createElement('div', { className: 'mb-4' },
          React.createElement('label', {
            className: 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1'
          }, isDirectory ? 'Output Directory' : 'Output File Path'),
          React.createElement('input', {
            type: 'text',
            value: path,
            onChange: (e) => setPath(e.target.value),
            className: 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500'
          })
        ),

        React.createElement('div', { className: 'flex justify-end gap-2' },
          React.createElement(Button, {
            onClick: onCancel,
            variant: 'secondary'
          }, 'Cancel'),
          React.createElement(Button, {
            onClick: () => onConfirm(path),
            variant: 'primary'
          }, 'Start')
        )
      )
    );
  }

  // Burn Dialog
  function BurnDialog({ drive, onClose }) {
    const [mode, setMode] = useState('iso'); // 'iso' or 'audio'
    const [isoPath, setIsoPath] = useState('');
    const [wavFiles, setWavFiles] = useState('');
    const [speed, setSpeed] = useState(0);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleBurn = async () => {
      setIsLoading(true);
      setError(null);
      try {
        if (mode === 'iso') {
          await api.burnIso(drive.device, isoPath, speed);
        } else {
          const files = wavFiles.split('\n').map(f => f.trim()).filter(f => f);
          await api.burnAudio(drive.device, files, speed);
        }
        onClose();
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };

    return React.createElement('div', {
      className: 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50'
    },
      React.createElement('div', {
        className: 'bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-full max-w-md'
      },
        React.createElement('div', { className: 'flex justify-between items-center mb-4' },
          React.createElement('h3', {
            className: 'text-lg font-semibold text-gray-900 dark:text-white'
          }, 'Burn Disc'),
          React.createElement('button', {
            onClick: onClose,
            className: 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
          }, React.createElement(Icons.X))
        ),

        // Mode selection
        React.createElement('div', { className: 'mb-4' },
          React.createElement('label', {
            className: 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2'
          }, 'Burn Type'),
          React.createElement('div', { className: 'flex gap-2' },
            React.createElement('button', {
              onClick: () => setMode('iso'),
              className: `flex-1 py-2 px-3 rounded-md text-sm font-medium ${
                mode === 'iso'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
              }`
            }, 'Data (ISO)'),
            React.createElement('button', {
              onClick: () => setMode('audio'),
              className: `flex-1 py-2 px-3 rounded-md text-sm font-medium ${
                mode === 'audio'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
              }`
            }, 'Audio CD')
          )
        ),

        // Source input
        mode === 'iso'
          ? React.createElement('div', { className: 'mb-4' },
              React.createElement('label', {
                className: 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1'
              }, 'ISO File Path'),
              React.createElement('input', {
                type: 'text',
                value: isoPath,
                onChange: (e) => setIsoPath(e.target.value),
                placeholder: '/storage/backups/image.iso',
                className: 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white'
              })
            )
          : React.createElement('div', { className: 'mb-4' },
              React.createElement('label', {
                className: 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1'
              }, 'WAV Files (one per line)'),
              React.createElement('textarea', {
                value: wavFiles,
                onChange: (e) => setWavFiles(e.target.value),
                placeholder: '/storage/music/track01.wav\n/storage/music/track02.wav',
                rows: 4,
                className: 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white'
              })
            ),

        // Speed selection
        React.createElement('div', { className: 'mb-4' },
          React.createElement('label', {
            className: 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1'
          }, 'Burn Speed'),
          React.createElement('select', {
            value: speed,
            onChange: (e) => setSpeed(parseInt(e.target.value)),
            className: 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white'
          },
            React.createElement('option', { value: 0 }, 'Auto (Recommended)'),
            React.createElement('option', { value: 4 }, '4x'),
            React.createElement('option', { value: 8 }, '8x'),
            React.createElement('option', { value: 16 }, '16x'),
            React.createElement('option', { value: 24 }, '24x')
          )
        ),

        // Error message
        error && React.createElement('div', {
          className: 'mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-md text-sm'
        }, error),

        // Actions
        React.createElement('div', { className: 'flex justify-end gap-2' },
          React.createElement(Button, {
            onClick: onClose,
            variant: 'secondary',
            disabled: isLoading
          }, 'Cancel'),
          React.createElement(Button, {
            onClick: handleBurn,
            variant: 'primary',
            disabled: isLoading || (mode === 'iso' && !isoPath) || (mode === 'audio' && !wavFiles)
          },
            isLoading ? React.createElement(Icons.Loader) : React.createElement(Icons.Flame),
            isLoading ? 'Starting...' : 'Start Burn'
          )
        )
      )
    );
  }

  // Job Card Component
  function JobCard({ job, onCancel, onRefresh }) {
    const [isCancelling, setIsCancelling] = useState(false);

    const handleCancel = async () => {
      setIsCancelling(true);
      try {
        await api.cancelJob(job.id);
        onRefresh();
      } catch (error) {
        console.error('Cancel failed:', error);
      } finally {
        setIsCancelling(false);
      }
    };

    const getJobTypeLabel = (jobType) => {
      const labels = {
        'read_iso': 'Reading ISO',
        'rip_audio': 'Ripping Audio',
        'rip_track': 'Ripping Track',
        'burn_iso': 'Burning ISO',
        'burn_audio': 'Burning Audio CD',
        'blank': 'Blanking Disc',
      };
      return labels[jobType] || jobType;
    };

    const getJobIcon = (jobType) => {
      switch (jobType) {
        case 'read_iso':
        case 'rip_audio':
        case 'rip_track':
          return Icons.Download;
        case 'burn_iso':
        case 'burn_audio':
          return Icons.Flame;
        case 'blank':
          return Icons.RefreshCw;
        default:
          return Icons.Disc;
      }
    };

    const getStatusColor = (status) => {
      switch (status) {
        case 'running': return 'text-blue-600 dark:text-blue-400';
        case 'completed': return 'text-green-600 dark:text-green-400';
        case 'failed': return 'text-red-600 dark:text-red-400';
        case 'cancelled': return 'text-gray-600 dark:text-gray-400';
        default: return 'text-yellow-600 dark:text-yellow-400';
      }
    };

    const JobIcon = getJobIcon(job.job_type);

    return React.createElement('div', {
      className: 'bg-white dark:bg-gray-800 rounded-lg shadow p-4 border border-gray-200 dark:border-gray-700'
    },
      React.createElement('div', { className: 'flex items-center justify-between mb-2' },
        React.createElement('div', { className: 'flex items-center gap-2' },
          React.createElement(JobIcon),
          React.createElement('span', { className: 'font-medium text-gray-900 dark:text-white' },
            getJobTypeLabel(job.job_type)
          ),
          React.createElement('span', { className: `text-sm ${getStatusColor(job.status)}` },
            job.status
          )
        ),
        job.status === 'running' && React.createElement(Button, {
          onClick: handleCancel,
          variant: 'danger',
          disabled: isCancelling
        },
          isCancelling ? React.createElement(Icons.Loader) : React.createElement(Icons.X),
          'Cancel'
        )
      ),

      // Progress bar for running jobs
      job.status === 'running' && React.createElement('div', null,
        React.createElement(ProgressBar, { progress: job.progress_percent }),
        React.createElement('div', { className: 'flex justify-between mt-1 text-sm text-gray-500 dark:text-gray-400' },
          React.createElement('span', null,
            job.current_track && job.total_tracks
              ? `Track ${job.current_track} of ${job.total_tracks}`
              : 'Processing...'
          ),
          React.createElement('span', null, `${Math.round(job.progress_percent)}%`)
        )
      ),

      // Error message for failed jobs
      job.status === 'failed' && job.error && React.createElement('div', {
        className: 'mt-2 p-2 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded text-sm'
      }, job.error),

      // Path info
      (job.input_path || job.output_path) && React.createElement('div', {
        className: 'mt-2 text-sm text-gray-500 dark:text-gray-400'
      },
        job.input_path && React.createElement('p', null,
          React.createElement('span', { className: 'font-medium' }, 'Source: '),
          job.input_path
        ),
        job.output_path && React.createElement('p', null,
          React.createElement('span', { className: 'font-medium' }, 'Output: '),
          job.output_path
        )
      )
    );
  }

  // Utility function to format bytes
  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  // Main Page Component
  function OpticalDrivePage() {
    const [drives, setDrives] = useState([]);
    const [jobs, setJobs] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
      try {
        const [drivesResponse, jobsResponse] = await Promise.all([
          api.getDrives(),
          api.getJobs(),
        ]);
        setDrives(drivesResponse.drives || []);
        setJobs(jobsResponse.jobs || []);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    }, []);

    useEffect(() => {
      fetchData();

      // Poll for updates every 2 seconds
      const interval = setInterval(fetchData, 2000);
      return () => clearInterval(interval);
    }, [fetchData]);

    const activeJobs = jobs.filter(j => j.status === 'running' || j.status === 'pending');
    const recentJobs = jobs.filter(j => j.status !== 'running' && j.status !== 'pending').slice(0, 5);

    if (isLoading) {
      return React.createElement('div', {
        className: 'flex items-center justify-center h-64'
      },
        React.createElement(Icons.Loader),
        React.createElement('span', { className: 'ml-2 text-gray-600 dark:text-gray-400' },
          'Loading drives...'
        )
      );
    }

    return React.createElement('div', { className: 'p-6' },
      // Header
      React.createElement('div', { className: 'flex items-center justify-between mb-6' },
        React.createElement('h1', {
          className: 'text-2xl font-bold text-gray-900 dark:text-white'
        }, 'Optical Drive Manager'),
        React.createElement(Button, {
          onClick: fetchData,
          variant: 'secondary'
        },
          React.createElement(Icons.RefreshCw),
          'Refresh'
        )
      ),

      // Error message
      error && React.createElement('div', {
        className: 'mb-6 p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg'
      }, error),

      // Drives section
      React.createElement('section', { className: 'mb-8' },
        React.createElement('h2', {
          className: 'text-lg font-semibold text-gray-900 dark:text-white mb-4'
        }, 'Drives'),
        drives.length === 0
          ? React.createElement('p', {
              className: 'text-gray-500 dark:text-gray-400 italic'
            }, 'No optical drives detected')
          : React.createElement('div', {
              className: 'grid gap-4 md:grid-cols-2'
            },
              drives.map(drive =>
                React.createElement(DriveCard, {
                  key: drive.device,
                  drive: drive,
                  onRefresh: fetchData
                })
              )
            )
      ),

      // Active Jobs section
      activeJobs.length > 0 && React.createElement('section', { className: 'mb-8' },
        React.createElement('h2', {
          className: 'text-lg font-semibold text-gray-900 dark:text-white mb-4'
        }, 'Active Jobs'),
        React.createElement('div', { className: 'space-y-4' },
          activeJobs.map(job =>
            React.createElement(JobCard, {
              key: job.id,
              job: job,
              onRefresh: fetchData
            })
          )
        )
      ),

      // Recent Jobs section
      recentJobs.length > 0 && React.createElement('section', null,
        React.createElement('h2', {
          className: 'text-lg font-semibold text-gray-900 dark:text-white mb-4'
        }, 'Recent Jobs'),
        React.createElement('div', { className: 'space-y-4' },
          recentJobs.map(job =>
            React.createElement(JobCard, {
              key: job.id,
              job: job,
              onRefresh: fetchData
            })
          )
        )
      )
    );
  }

  // Dashboard Widget
  function OpticalDriveWidget() {
    const [drives, setDrives] = useState([]);
    const [jobs, setJobs] = useState([]);

    useEffect(() => {
      const fetchData = async () => {
        try {
          const [drivesResponse, jobsResponse] = await Promise.all([
            api.getDrives(),
            api.getJobs(),
          ]);
          setDrives(drivesResponse.drives || []);
          setJobs(jobsResponse.jobs || []);
        } catch (err) {
          console.error('Failed to fetch optical drive data:', err);
        }
      };

      fetchData();
      const interval = setInterval(fetchData, 5000);
      return () => clearInterval(interval);
    }, []);

    const activeJobs = jobs.filter(j => j.status === 'running');
    const readyDrives = drives.filter(d => d.is_ready);

    return React.createElement('div', {
      className: 'bg-white dark:bg-gray-800 rounded-lg shadow p-4'
    },
      React.createElement('div', { className: 'flex items-center gap-2 mb-3' },
        React.createElement('div', {
          className: 'p-2 bg-blue-100 dark:bg-blue-900 rounded-lg text-blue-600 dark:text-blue-400'
        }, React.createElement(Icons.Disc)),
        React.createElement('h3', {
          className: 'font-semibold text-gray-900 dark:text-white'
        }, 'Optical Drives')
      ),

      React.createElement('div', { className: 'space-y-2 text-sm' },
        React.createElement('p', { className: 'text-gray-600 dark:text-gray-400' },
          `${drives.length} drive${drives.length !== 1 ? 's' : ''} detected`
        ),
        readyDrives.length > 0 && React.createElement('p', {
          className: 'text-green-600 dark:text-green-400'
        },
          `${readyDrives.length} with media`
        ),
        activeJobs.length > 0 && React.createElement('div', null,
          React.createElement('p', { className: 'text-blue-600 dark:text-blue-400 mb-1' },
            `${activeJobs.length} active job${activeJobs.length !== 1 ? 's' : ''}`
          ),
          activeJobs[0] && React.createElement(ProgressBar, {
            progress: activeJobs[0].progress_percent,
            className: 'mt-1'
          })
        )
      )
    );
  }

// Register plugin components (for dashboard widget compatibility)
window.BaluHostPlugins = window.BaluHostPlugins || {};
window.BaluHostPlugins[PLUGIN_NAME] = {
  // Main page component
  routes: {
    'drives': OpticalDrivePage,
  },
  // Dashboard widgets
  widgets: {
    'OpticalDriveWidget': OpticalDriveWidget,
  },
};

// Export components for ES6 module loading
export default OpticalDrivePage;
export { OpticalDrivePage, OpticalDriveWidget };

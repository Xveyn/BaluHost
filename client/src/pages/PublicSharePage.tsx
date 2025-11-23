import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  getShareLinkInfo, 
  accessShareLink, 
  type ShareLinkInfo, 
  type ShareLinkAccessResponse 
} from '../api/shares';
import { apiClient } from '../lib/api';
import { Download, Lock, Eye, FileIcon, Calendar, AlertCircle } from 'lucide-react';

export default function PublicSharePage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  
  const [info, setInfo] = useState<ShareLinkInfo | null>(null);
  const [accessData, setAccessData] = useState<ShareLinkAccessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [password, setPassword] = useState('');
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (token) {
      loadShareInfo();
    }
  }, [token]);

  const loadShareInfo = async () => {
    if (!token) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await getShareLinkInfo(token);
      setInfo(data);
      
      if (!data.is_accessible) {
        if (data.is_expired) {
          setError('This share link has expired');
        } else {
          setError('This share link is no longer accessible');
        }
      } else if (data.has_password) {
        setPasswordRequired(true);
      } else {
        // No password required, access directly
        await handleAccess();
      }
    } catch (err: any) {
      console.error('Failed to load share info:', err);
      setError(err.response?.data?.detail || 'Failed to load share information');
    } finally {
      setLoading(false);
    }
  };

  const handleAccess = async (pwd?: string) => {
    if (!token) return;
    
    setError(null);
    
    try {
      const data = await accessShareLink(token, { password: pwd || password });
      setAccessData(data);
      setPasswordRequired(false);
    } catch (err: any) {
      console.error('Failed to access share:', err);
      if (err.response?.status === 403) {
        setError('Invalid password');
      } else {
        setError(err.response?.data?.detail || 'Failed to access share');
      }
    }
  };

  const handlePasswordSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleAccess();
  };

  const handleDownload = async () => {
    if (!accessData || !token) return;
    
    setDownloading(true);
    setError(null);
    
    try {
      const response = await apiClient.get(`/files/download/${accessData.file_id}`, {
        responseType: 'blob',
        headers: {
          'X-Share-Token': token,
          'X-Share-Password': password || undefined
        }
      });

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', accessData.file_name || 'download');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      console.error('Download failed:', err);
      setError(err.response?.data?.detail || 'Failed to download file');
    } finally {
      setDownloading(false);
    }
  };

  const formatFileSize = (bytes: number | null) => {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`;
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading share...</p>
        </div>
      </div>
    );
  }

  if (error && !info) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full text-center">
          <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h1>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Go to Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-lg overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-blue-700 p-6 text-white">
            <h1 className="text-2xl font-bold mb-2">Shared File</h1>
            <p className="text-blue-100">Someone has shared a file with you</p>
          </div>

          {/* Content */}
          <div className="p-6">
            {passwordRequired && !accessData ? (
              // Password Form
              <div>
                <div className="text-center mb-6">
                  <Lock className="w-16 h-16 text-blue-600 mx-auto mb-4" />
                  <h2 className="text-xl font-semibold mb-2">Password Required</h2>
                  <p className="text-gray-600">
                    This share is password protected. Please enter the password to access it.
                  </p>
                </div>

                <form onSubmit={handlePasswordSubmit} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Password</label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter password"
                      className="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                      required
                      autoFocus
                    />
                  </div>

                  {error && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
                  >
                    Access File
                  </button>
                </form>

                {/* File Info Preview */}
                {info && (
                  <div className="mt-6 pt-6 border-t">
                    <div className="flex items-center justify-between text-sm text-gray-600">
                      <span className="flex items-center">
                        <FileIcon className="w-4 h-4 mr-2" />
                        {info.file_name}
                      </span>
                      <span>{formatFileSize(info.file_size)}</span>
                    </div>
                    {info.expires_at && (
                      <div className="flex items-center text-sm text-gray-500 mt-2">
                        <Calendar className="w-4 h-4 mr-2" />
                        Expires: {formatDate(info.expires_at)}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : accessData ? (
              // File Access View
              <div>
                {/* File Info */}
                <div className="bg-gray-50 rounded-lg p-6 mb-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-start">
                      <FileIcon className="w-12 h-12 text-blue-600 mr-4 flex-shrink-0" />
                      <div>
                        <h2 className="text-xl font-semibold text-gray-900 mb-1">
                          {accessData.file_name}
                        </h2>
                        <p className="text-gray-600">
                          {formatFileSize(accessData.file_size)}
                        </p>
                      </div>
                    </div>
                  </div>

                  {accessData.description && (
                    <div className="mt-4 p-3 bg-white rounded border">
                      <p className="text-sm text-gray-700">{accessData.description}</p>
                    </div>
                  )}

                  {info?.expires_at && (
                    <div className="flex items-center text-sm text-gray-500 mt-4">
                      <Calendar className="w-4 h-4 mr-2" />
                      Expires: {formatDate(info.expires_at)}
                    </div>
                  )}
                </div>

                {error && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm mb-4">
                    {error}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-3">
                  {accessData.allow_preview && (
                    <button
                      className="flex-1 px-4 py-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-medium flex items-center justify-center"
                      onClick={() => {/* TODO: Implement preview */}}
                    >
                      <Eye className="w-5 h-5 mr-2" />
                      Preview
                    </button>
                  )}
                  {accessData.allow_download && (
                    <button
                      onClick={handleDownload}
                      disabled={downloading}
                      className="flex-1 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium flex items-center justify-center disabled:opacity-50"
                    >
                      <Download className="w-5 h-5 mr-2" />
                      {downloading ? 'Downloading...' : 'Download'}
                    </button>
                  )}
                </div>

                {!accessData.allow_download && !accessData.allow_preview && (
                  <p className="text-center text-gray-500 mt-4">
                    This file cannot be downloaded or previewed.
                  </p>
                )}
              </div>
            ) : null}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-6 text-gray-500 text-sm">
          <p>Powered by BaluHost NAS Manager</p>
        </div>
      </div>
    </div>
  );
}

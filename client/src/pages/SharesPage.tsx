import { useState, useEffect } from 'react';
import {
  listShareLinks,
  listFileShares,
  listFilesSharedWithMe,
  getShareStatistics,
  deleteShareLink,
  deleteFileShare,
  type ShareLink,
  type FileShare,
  type SharedWithMe,
  type ShareStatistics
} from '../api/shares';
import { Link2, Users, Share2, Trash2, Copy, ExternalLink, CheckCircle, Edit, Search, Filter, QrCode } from 'lucide-react';
import CreateShareLinkModal from '../components/CreateShareLinkModal';
import CreateFileShareModal from '../components/CreateFileShareModal';
import EditShareLinkModal from '../components/EditShareLinkModal';
import EditFileShareModal from '../components/EditFileShareModal';

export default function SharesPage() {
  const [activeTab, setActiveTab] = useState<'links' | 'shares' | 'shared-with-me'>('links');
  const [shareLinks, setShareLinks] = useState<ShareLink[]>([]);
  const [fileShares, setFileShares] = useState<FileShare[]>([]);
  const [sharedWithMe, setSharedWithMe] = useState<SharedWithMe[]>([]);
  const [statistics, setStatistics] = useState<ShareStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreateLinkModal, setShowCreateLinkModal] = useState(false);
  const [showCreateShareModal, setShowCreateShareModal] = useState(false);
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  
  // Edit modals
  const [editingLink, setEditingLink] = useState<ShareLink | null>(null);
  const [editingShare, setEditingShare] = useState<FileShare | null>(null);
  
  // Filter and search
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'expired'>('all');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    loadData();
  }, [activeTab]);

  const loadData = async () => {
    setLoading(true);
    try {
      const stats = await getShareStatistics();
      setStatistics(stats);

      if (activeTab === 'links') {
        const links = await listShareLinks(true);
        setShareLinks(links);
      } else if (activeTab === 'shares') {
        const shares = await listFileShares();
        setFileShares(shares);
      } else {
        const shared = await listFilesSharedWithMe();
        setSharedWithMe(shared);
      }
    } catch (error) {
      console.error('Failed to load shares:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteShareLink = async (linkId: number) => {
    if (!confirm('Are you sure you want to delete this share link?')) return;
    
    try {
      await deleteShareLink(linkId);
      await loadData();
    } catch (error) {
      console.error('Failed to delete share link:', error);
      alert('Failed to delete share link');
    }
  };

  const handleDeleteFileShare = async (shareId: number) => {
    if (!confirm('Are you sure you want to revoke this file share?')) return;
    
    try {
      await deleteFileShare(shareId);
      await loadData();
    } catch (error) {
      console.error('Failed to delete file share:', error);
      alert('Failed to revoke file share');
    }
  };

  const copyShareLink = (token: string) => {
    const url = `${window.location.origin}/share/${token}`;
    navigator.clipboard.writeText(url);
    setCopiedToken(token);
    setTimeout(() => setCopiedToken(null), 2000);
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString();
  };

  const formatFileSize = (bytes: number | null) => {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`;
  };

  // Filter and search logic with safety checks
  const filteredShareLinks = Array.isArray(shareLinks) ? shareLinks.filter(link => {
    // Status filter
    if (statusFilter === 'active' && (link.is_expired || !link.is_accessible)) return false;
    if (statusFilter === 'expired' && !link.is_expired) return false;
    
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        link.file_name?.toLowerCase().includes(query) ||
        link.description?.toLowerCase().includes(query)
      );
    }
    
    return true;
  }) : [];

  const filteredFileShares = Array.isArray(fileShares) ? fileShares.filter(share => {
    // Status filter
    if (statusFilter === 'active' && share.is_expired) return false;
    if (statusFilter === 'expired' && !share.is_expired) return false;
    
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        share.file_name?.toLowerCase().includes(query) ||
        share.shared_with_username?.toLowerCase().includes(query)
      );
    }
    
    return true;
  }) : [];

  const filteredSharedWithMe = Array.isArray(sharedWithMe) ? sharedWithMe.filter(item => {
    // Status filter
    if (statusFilter === 'active' && item.is_expired) return false;
    if (statusFilter === 'expired' && !item.is_expired) return false;
    
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        item.file_name.toLowerCase().includes(query) ||
        item.owner_username.toLowerCase().includes(query)
      );
    }
    
    return true;
  }) : [];

  const generateQRCode = (token: string) => {
    const url = `${window.location.origin}/share/${token}`;
    window.open(`https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(url)}`, '_blank');
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
          File Sharing
        </h1>
        <p className="text-gray-600">Manage public share links and user file shares</p>
      </div>

      {/* Statistics Cards */}
      {statistics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white/5 backdrop-blur-sm p-5 rounded-xl border border-white/10 hover:bg-white/10 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-blue-400 uppercase tracking-wide mb-1">Active Share Links</p>
                <p className="text-3xl font-bold text-white">{statistics.active_share_links}</p>
                <p className="text-xs text-gray-400 mt-1">of {statistics.total_share_links} total</p>
              </div>
              <div className="bg-blue-500/20 p-3 rounded-lg">
                <Link2 className="w-6 h-6 text-blue-400" />
              </div>
            </div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm p-5 rounded-xl border border-white/10 hover:bg-white/10 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-green-400 uppercase tracking-wide mb-1">Total Downloads</p>
                <p className="text-3xl font-bold text-white">{statistics.total_downloads}</p>
                <p className="text-xs text-gray-400 mt-1">all time</p>
              </div>
              <div className="bg-green-500/20 p-3 rounded-lg">
                <ExternalLink className="w-6 h-6 text-green-400" />
              </div>
            </div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm p-5 rounded-xl border border-white/10 hover:bg-white/10 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-purple-400 uppercase tracking-wide mb-1">Active File Shares</p>
                <p className="text-3xl font-bold text-white">{statistics.active_file_shares}</p>
                <p className="text-xs text-gray-400 mt-1">of {statistics.total_file_shares} total</p>
              </div>
              <div className="bg-purple-500/20 p-3 rounded-lg">
                <Users className="w-6 h-6 text-purple-400" />
              </div>
            </div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm p-5 rounded-xl border border-white/10 hover:bg-white/10 transition-all">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-orange-400 uppercase tracking-wide mb-1">Shared With Me</p>
                <p className="text-3xl font-bold text-white">{statistics.files_shared_with_me}</p>
                <p className="text-xs text-gray-400 mt-1">files accessible</p>
              </div>
              <div className="bg-orange-500/20 p-3 rounded-lg">
                <Share2 className="w-6 h-6 text-orange-400" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 mb-6 overflow-hidden">
        <div className="flex">
          <button
            onClick={() => setActiveTab('links')}
            className={`flex-1 px-6 py-4 font-medium transition-all relative ${
              activeTab === 'links'
                ? 'text-blue-400 bg-white/5'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <Link2 className="w-5 h-5" />
              <span>Public Share Links</span>
            </div>
            {activeTab === 'links' && (
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-blue-600" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('shares')}
            className={`flex-1 px-6 py-4 font-medium transition-all relative ${
              activeTab === 'shares'
                ? 'text-blue-400 bg-white/5'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <Users className="w-5 h-5" />
              <span>User Shares</span>
            </div>
            {activeTab === 'shares' && (
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-blue-600" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('shared-with-me')}
            className={`flex-1 px-6 py-4 font-medium transition-all relative ${
              activeTab === 'shared-with-me'
                ? 'text-blue-400 bg-white/5'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <Share2 className="w-5 h-5" />
              <span>Shared With Me</span>
            </div>
            {activeTab === 'shared-with-me' && (
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-blue-600" />
            )}
          </button>
        </div>

        <div className="p-6">
          {/* Search and Filter Bar */}
          <div className="mb-6 space-y-3">
            <div className="flex gap-3">
              {/* Search */}
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by file name or description..."
                  className="w-full pl-11 pr-4 py-3 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-white placeholder-gray-400"
                />
              </div>

              {/* Filter Toggle */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`px-5 py-3 border rounded-xl hover:bg-white/10 flex items-center gap-2 font-medium transition-all ${
                  showFilters ? 'bg-blue-500/20 border-blue-500/50 text-blue-400' : 'border-white/10 text-gray-300'
                }`}
              >
                <Filter className="w-5 h-5" />
                <span>Filters</span>
              </button>

              {/* Action Button */}
              {activeTab === 'links' && (
                <button
                  onClick={() => setShowCreateLinkModal(true)}
                  className="px-5 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-xl hover:from-blue-700 hover:to-blue-800 shadow-lg hover:shadow-xl transition-all font-medium flex items-center gap-2"
                >
                  <Link2 className="w-5 h-5" />
                  <span>Create Link</span>
                </button>
              )}
              {activeTab === 'shares' && (
                <button
                  onClick={() => setShowCreateShareModal(true)}
                  className="px-5 py-3 bg-gradient-to-r from-purple-600 to-purple-700 text-white rounded-xl hover:from-purple-700 hover:to-purple-800 shadow-lg hover:shadow-xl transition-all font-medium flex items-center gap-2"
                >
                  <Users className="w-5 h-5" />
                  <span>Share with User</span>
                </button>
              )}
            </div>

            {/* Filter Options */}
            {showFilters && (
              <div className="flex gap-3 p-4 bg-white/5 backdrop-blur-sm rounded-xl border border-white/10">
                <span className="text-sm font-semibold text-gray-300 flex items-center">
                  Status:
                </span>
                <label className="flex items-center cursor-pointer">
                  <input
                    type="radio"
                    value="all"
                    checked={statusFilter === 'all'}
                    onChange={(e) => setStatusFilter(e.target.value as any)}
                    className="mr-2 w-4 h-4 text-blue-500"
                  />
                  <span className="text-sm font-medium text-gray-300">All</span>
                </label>
                <label className="flex items-center cursor-pointer">
                  <input
                    type="radio"
                    value="active"
                    checked={statusFilter === 'active'}
                    onChange={(e) => setStatusFilter(e.target.value as any)}
                    className="mr-2 w-4 h-4 text-blue-500"
                  />
                  <span className="text-sm font-medium text-gray-300">Active</span>
                </label>
                <label className="flex items-center cursor-pointer">
                  <input
                    type="radio"
                    value="expired"
                    checked={statusFilter === 'expired'}
                    onChange={(e) => setStatusFilter(e.target.value as any)}
                    className="mr-2 w-4 h-4 text-blue-500"
                  />
                  <span className="text-sm font-medium text-gray-300">Expired</span>
                </label>
              </div>
            )}
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-16">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
              <p className="text-gray-600 font-medium">Loading shares...</p>
            </div>
          ) : (
            <>
              {/* Share Links Table */}
              {activeTab === 'links' && (
                <div className="overflow-x-auto rounded-lg">
                  {filteredShareLinks.length === 0 ? (
                    <div className="text-center py-16">
                      <Link2 className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                      <h3 className="text-lg font-semibold text-gray-300 mb-2">
                        {shareLinks.length === 0 ? 'No share links yet' : 'No matching share links found'}
                      </h3>
                      <p className="text-gray-500 mb-6">
                        {shareLinks.length === 0 
                          ? 'Create your first public share link to get started' 
                          : 'Try adjusting your search or filters'}
                      </p>
                      {shareLinks.length === 0 && (
                        <button
                          onClick={() => setShowCreateLinkModal(true)}
                          className="px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-xl hover:from-blue-700 hover:to-blue-800 shadow-lg hover:shadow-xl transition-all font-medium"
                        >
                          Create Your First Link
                        </button>
                      )}
                    </div>
                  ) : (
                    <table className="min-w-full">
                      <thead className="bg-white/5 backdrop-blur-sm border-b border-white/10">
                        <tr>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">File</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Status</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Downloads</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Expires</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Created</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {filteredShareLinks.map((link) => (
                          <tr key={link.id} className={`hover:bg-white/5 transition-colors ${link.is_expired ? 'opacity-60' : ''}`}>
                            <td className="px-6 py-4">
                              <div className="font-semibold text-white">{link.file_name}</div>
                              <div className="text-sm text-gray-400 mt-0.5">
                                {formatFileSize(link.file_size)}
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex flex-wrap gap-1.5">
                                {link.is_expired ? (
                                  <span className="px-3 py-1 bg-red-100 text-red-700 rounded-full text-xs font-semibold">
                                    Expired
                                  </span>
                                ) : link.is_accessible ? (
                                  <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-xs font-semibold">
                                    Active
                                  </span>
                                ) : (
                                  <span className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded-full text-xs font-semibold">
                                    Limited
                                  </span>
                                )}
                                {link.has_password && (
                                  <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-semibold">
                                    🔒 Protected
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300 font-medium">
                              {link.download_count}
                              {link.max_downloads && ` / ${link.max_downloads}`}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300 font-medium">
                              {formatDate(link.expires_at)}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300 font-medium">
                              {formatDate(link.created_at)}
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex space-x-1.5">
                                <button
                                  onClick={() => copyShareLink(link.token)}
                                  className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                                  title="Copy link"
                                >
                                  {copiedToken === link.token ? (
                                    <CheckCircle className="w-5 h-5" />
                                  ) : (
                                    <Copy className="w-5 h-5" />
                                  )}
                                </button>
                                <button
                                  onClick={() => generateQRCode(link.token)}
                                  className="p-2 text-purple-600 hover:bg-purple-50 rounded-lg transition-colors"
                                  title="Generate QR Code"
                                >
                                  <QrCode className="w-5 h-5" />
                                </button>
                                <button
                                  onClick={() => setEditingLink(link)}
                                  className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                                  title="Edit"
                                >
                                  <Edit className="w-5 h-5" />
                                </button>
                                <button
                                  onClick={() => handleDeleteShareLink(link.id)}
                                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                  title="Delete"
                                >
                                  <Trash2 className="w-5 h-5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* File Shares Table */}
              {activeTab === 'shares' && (
                <div className="overflow-x-auto">
                  {filteredFileShares.length === 0 ? (
                    <p className="text-gray-500 text-center py-8">
                      {fileShares.length === 0 ? 'No file shares yet' : 'No matching file shares found'}
                    </p>
                  ) : (
                    <table className="min-w-full">
                      <thead className="bg-white/5 backdrop-blur-sm border-b border-white/10">
                        <tr>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">File</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Shared With</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Permissions</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Expires</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {filteredFileShares.map((share) => (
                          <tr key={share.id} className="hover:bg-white/5 transition-colors">
                            <td className="px-6 py-4">
                              <div className="font-semibold text-white">{share.file_name}</div>
                              <div className="text-sm text-gray-400 mt-0.5">
                                {formatFileSize(share.file_size)}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-gray-300 font-medium">{share.shared_with_username}</td>
                            <td className="px-6 py-4">
                              <div className="flex space-x-1">
                                {share.can_read && (
                                  <span className="px-2.5 py-1 bg-blue-500/20 text-blue-400 rounded-full text-xs font-semibold">
                                    Read
                                  </span>
                                )}
                                {share.can_write && (
                                  <span className="px-2.5 py-1 bg-green-500/20 text-green-400 rounded-full text-xs font-semibold">
                                    Write
                                  </span>
                                )}
                                {share.can_delete && (
                                  <span className="px-2.5 py-1 bg-red-500/20 text-red-400 rounded-full text-xs font-semibold">
                                    Delete
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300 font-medium">
                              {formatDate(share.expires_at)}
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex space-x-1">
                                <button
                                  onClick={() => setEditingShare(share)}
                                  className="p-2 text-green-400 hover:bg-green-500/20 rounded-lg transition-colors"
                                  title="Edit permissions"
                                >
                                  <Edit className="w-5 h-5" />
                                </button>
                                <button
                                  onClick={() => handleDeleteFileShare(share.id)}
                                  className="p-2 text-red-400 hover:bg-red-500/20 rounded-lg transition-colors"
                                  title="Revoke"
                                >
                                  <Trash2 className="w-5 h-5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* Shared With Me Table */}
              {activeTab === 'shared-with-me' && (
                <div className="overflow-x-auto">
                  {filteredSharedWithMe.length === 0 ? (
                    <p className="text-gray-500 text-center py-8">
                      {sharedWithMe.length === 0 ? 'No files shared with you' : 'No matching shared files found'}
                    </p>
                  ) : (
                    <table className="min-w-full">
                      <thead className="bg-white/5 backdrop-blur-sm border-b border-white/10">
                        <tr>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">File</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Owner</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Permissions</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Shared</th>
                          <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Expires</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {filteredSharedWithMe.map((item) => (
                          <tr key={item.share_id} className="hover:bg-white/5 transition-colors">
                            <td className="px-6 py-4">
                              <div className="font-semibold text-white">{item.file_name}</div>
                              <div className="text-sm text-gray-400 mt-0.5">
                                {formatFileSize(item.file_size)}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-gray-300 font-medium">{item.owner_username}</td>
                            <td className="px-6 py-4">
                              <div className="flex space-x-1">
                                {item.can_read && (
                                  <span className="px-2.5 py-1 bg-blue-500/20 text-blue-400 rounded-full text-xs font-semibold">
                                    Read
                                  </span>
                                )}
                                {item.can_write && (
                                  <span className="px-2.5 py-1 bg-green-500/20 text-green-400 rounded-full text-xs font-semibold">
                                    Write
                                  </span>
                                )}
                                {item.can_delete && (
                                  <span className="px-2.5 py-1 bg-red-500/20 text-red-400 rounded-full text-xs font-semibold">
                                    Delete
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300 font-medium">
                              {formatDate(item.shared_at)}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300 font-medium">
                              {formatDate(item.expires_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      {showCreateLinkModal && (
        <CreateShareLinkModal
          onClose={() => setShowCreateLinkModal(false)}
          onSuccess={() => {
            setShowCreateLinkModal(false);
            loadData();
          }}
        />
      )}
      {showCreateShareModal && (
        <CreateFileShareModal
          onClose={() => setShowCreateShareModal(false)}
          onSuccess={() => {
            setShowCreateShareModal(false);
            loadData();
          }}
        />
      )}
      {editingLink && (
        <EditShareLinkModal
          shareLink={editingLink}
          onClose={() => setEditingLink(null)}
          onSuccess={() => {
            setEditingLink(null);
            loadData();
          }}
        />
      )}
      {editingShare && (
        <EditFileShareModal
          fileShare={editingShare}
          onClose={() => setEditingShare(null)}
          onSuccess={() => {
            setEditingShare(null);
            loadData();
          }}
        />
      )}
    </div>
  );
}

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
import { Link2, Users, Share2, Trash2, Copy, CheckCircle, Edit, Search, Filter, QrCode, Calendar, Download } from 'lucide-react';
import CreateShareLinkModal from '../components/CreateShareLinkModal';
import CreateFileShareModal from '../components/CreateFileShareModal';
import EditShareLinkModal from '../components/EditShareLinkModal';
import EditFileShareModal from '../components/EditFileShareModal';

export default function SharesPage() {
  // User list for modal
  const [users, setUsers] = useState<any[]>([]);
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
    fetchUsers();
  }, [activeTab]);

  const fetchUsers = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const response = await fetch('/api/users/', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      if (Array.isArray(data.users)) {
        setUsers(data.users);
      } else {
        setUsers([]);
      }
    } catch (err) {
      setUsers([]);
    }
  };

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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">File Sharing</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">Manage public share links and user file shares</p>
        </div>
      </div>

      {/* Statistics Cards */}
      {statistics && (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
            <div className="flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs sm:text-sm text-slate-400 truncate">Active Links</p>
                <p className="mt-1 text-xl sm:text-2xl font-semibold text-white">{statistics.active_share_links}</p>
                <p className="text-xs text-slate-500 mt-0.5">of {statistics.total_share_links} total</p>
              </div>
              <div className="rounded-lg bg-sky-500/20 p-2 sm:p-3 flex-shrink-0 ml-2">
                <Link2 className="h-5 w-5 sm:h-6 sm:w-6 text-sky-400" />
              </div>
            </div>
          </div>
          <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
            <div className="flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs sm:text-sm text-slate-400 truncate">Downloads</p>
                <p className="mt-1 text-xl sm:text-2xl font-semibold text-white">{statistics.total_downloads}</p>
                <p className="text-xs text-slate-500 mt-0.5">all time</p>
              </div>
              <div className="rounded-lg bg-green-500/20 p-2 sm:p-3 flex-shrink-0 ml-2">
                <Download className="h-5 w-5 sm:h-6 sm:w-6 text-green-400" />
              </div>
            </div>
          </div>
          <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
            <div className="flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs sm:text-sm text-slate-400 truncate">User Shares</p>
                <p className="mt-1 text-xl sm:text-2xl font-semibold text-white">{statistics.active_file_shares}</p>
                <p className="text-xs text-slate-500 mt-0.5">of {statistics.total_file_shares} total</p>
              </div>
              <div className="rounded-lg bg-purple-500/20 p-2 sm:p-3 flex-shrink-0 ml-2">
                <Users className="h-5 w-5 sm:h-6 sm:w-6 text-purple-400" />
              </div>
            </div>
          </div>
          <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
            <div className="flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs sm:text-sm text-slate-400 truncate">Shared With Me</p>
                <p className="mt-1 text-xl sm:text-2xl font-semibold text-white">{statistics.files_shared_with_me}</p>
                <p className="text-xs text-slate-500 mt-0.5">files accessible</p>
              </div>
              <div className="rounded-lg bg-orange-500/20 p-2 sm:p-3 flex-shrink-0 ml-2">
                <Share2 className="h-5 w-5 sm:h-6 sm:w-6 text-orange-400" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="card border-slate-800/60 bg-slate-900/55 overflow-hidden">
        <div className="overflow-x-auto border-b border-slate-800/60">
          <div className="flex min-w-max">
            <button
              onClick={() => setActiveTab('links')}
              className={`flex-1 min-w-[120px] px-4 sm:px-6 py-3 sm:py-4 font-medium transition-all relative text-sm sm:text-base ${
                activeTab === 'links'
                  ? 'text-sky-400 bg-slate-800/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'
              }`}
            >
              <div className="flex items-center justify-center gap-2">
                <Link2 className="w-4 h-4 sm:w-5 sm:h-5" />
                <span className="hidden sm:inline">Public Share Links</span>
                <span className="sm:hidden">Links</span>
              </div>
              {activeTab === 'links' && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-sky-500" />
              )}
            </button>
            <button
              onClick={() => setActiveTab('shares')}
              className={`flex-1 min-w-[120px] px-4 sm:px-6 py-3 sm:py-4 font-medium transition-all relative text-sm sm:text-base ${
                activeTab === 'shares'
                  ? 'text-sky-400 bg-slate-800/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'
              }`}
            >
              <div className="flex items-center justify-center gap-2">
                <Users className="w-4 h-4 sm:w-5 sm:h-5" />
                <span className="hidden sm:inline">User Shares</span>
                <span className="sm:hidden">Shares</span>
              </div>
              {activeTab === 'shares' && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-sky-500" />
              )}
            </button>
            <button
              onClick={() => setActiveTab('shared-with-me')}
              className={`flex-1 min-w-[120px] px-4 sm:px-6 py-3 sm:py-4 font-medium transition-all relative text-sm sm:text-base ${
                activeTab === 'shared-with-me'
                  ? 'text-sky-400 bg-slate-800/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'
              }`}
            >
              <div className="flex items-center justify-center gap-2">
                <Share2 className="w-4 h-4 sm:w-5 sm:h-5" />
                <span className="hidden sm:inline">Shared With Me</span>
                <span className="sm:hidden">Received</span>
              </div>
              {activeTab === 'shared-with-me' && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-sky-500" />
              )}
            </button>
          </div>
        </div>

        <div className="p-4 sm:p-6">
          {/* Search and Filter Bar */}
          <div className="mb-4 sm:mb-6 space-y-3">
            <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
              {/* Search */}
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 sm:w-5 sm:h-5 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by file name..."
                  className="w-full pl-10 sm:pl-11 pr-4 py-2.5 sm:py-3 border border-slate-700 bg-slate-900/70 rounded-xl focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-slate-200 placeholder-slate-500 text-sm sm:text-base"
                />
              </div>

              {/* Filter Toggle */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`px-4 sm:px-5 py-2.5 sm:py-3 border rounded-xl flex items-center justify-center gap-2 font-medium transition-all touch-manipulation active:scale-95 text-sm sm:text-base ${
                  showFilters ? 'bg-sky-500/20 border-sky-500/50 text-sky-400' : 'border-slate-700 text-slate-300 hover:bg-slate-800/50'
                }`}
              >
                <Filter className="w-4 h-4 sm:w-5 sm:h-5" />
                <span>Filters</span>
              </button>

              {/* Action Button */}
              {activeTab === 'links' && (
                <button
                  onClick={() => setShowCreateLinkModal(true)}
                  className="btn btn-primary flex items-center justify-center gap-2 touch-manipulation active:scale-95"
                >
                  <Link2 className="w-4 h-4 sm:w-5 sm:h-5" />
                  <span className="hidden sm:inline">Create Link</span>
                  <span className="sm:hidden">Create</span>
                </button>
              )}
              {activeTab === 'shares' && (
                <button
                  onClick={() => setShowCreateShareModal(true)}
                  className="btn btn-primary flex items-center justify-center gap-2 touch-manipulation active:scale-95"
                >
                  <Users className="w-4 h-4 sm:w-5 sm:h-5" />
                  <span className="hidden sm:inline">Share with User</span>
                  <span className="sm:hidden">Share</span>
                </button>
              )}
            </div>

            {/* Filter Options */}
            {showFilters && (
              <div className="flex flex-wrap gap-2 sm:gap-3 p-3 sm:p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
                <span className="text-xs sm:text-sm font-semibold text-slate-300 flex items-center mr-2">
                  Status:
                </span>
                {(['all', 'active', 'expired'] as const).map((status) => (
                  <label key={status} className="flex items-center cursor-pointer">
                    <input
                      type="radio"
                      value={status}
                      checked={statusFilter === status}
                      onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
                      className="mr-1.5 sm:mr-2 w-4 h-4 text-sky-500"
                    />
                    <span className="text-xs sm:text-sm font-medium text-slate-300 capitalize">{status}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 sm:py-16">
              <div className="animate-spin rounded-full h-10 w-10 sm:h-12 sm:w-12 border-b-2 border-sky-500 mb-4"></div>
              <p className="text-slate-400 font-medium text-sm sm:text-base">Loading shares...</p>
            </div>
          ) : (
            <>
              {/* Share Links Tab */}
              {activeTab === 'links' && (
                <>
                  {filteredShareLinks.length === 0 ? (
                    <div className="text-center py-12 sm:py-16">
                      <Link2 className="w-12 h-12 sm:w-16 sm:h-16 text-slate-600 mx-auto mb-4" />
                      <h3 className="text-base sm:text-lg font-semibold text-slate-300 mb-2">
                        {shareLinks.length === 0 ? 'No share links yet' : 'No matching share links found'}
                      </h3>
                      <p className="text-slate-500 mb-6 text-sm sm:text-base">
                        {shareLinks.length === 0
                          ? 'Create your first public share link to get started'
                          : 'Try adjusting your search or filters'}
                      </p>
                      {shareLinks.length === 0 && (
                        <button
                          onClick={() => setShowCreateLinkModal(true)}
                          className="btn btn-primary touch-manipulation active:scale-95"
                        >
                          Create Your First Link
                        </button>
                      )}
                    </div>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      <div className="hidden lg:block overflow-x-auto rounded-lg">
                        <table className="min-w-full">
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">File</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Downloads</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Expires</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Created</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Actions</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60">
                            {filteredShareLinks.map((link) => (
                              <tr key={link.id} className={`hover:bg-slate-800/30 transition-colors ${link.is_expired ? 'opacity-60' : ''}`}>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="font-semibold text-white">{link.file_name}</div>
                                  <div className="text-xs sm:text-sm text-slate-400 mt-0.5">
                                    {formatFileSize(link.file_size)}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex flex-wrap gap-1.5">
                                    {link.is_expired ? (
                                      <span className="px-2.5 py-1 rounded-full text-xs font-semibold border border-red-500/40 bg-red-500/15 text-red-300">
                                        Expired
                                      </span>
                                    ) : link.is_accessible ? (
                                      <span className="px-2.5 py-1 rounded-full text-xs font-semibold border border-green-500/40 bg-green-500/15 text-green-300">
                                        Active
                                      </span>
                                    ) : (
                                      <span className="px-2.5 py-1 rounded-full text-xs font-semibold border border-yellow-500/40 bg-yellow-500/15 text-yellow-300">
                                        Limited
                                      </span>
                                    )}
                                    {link.has_password && (
                                      <span className="px-2.5 py-1 rounded-full text-xs font-semibold border border-sky-500/40 bg-sky-500/15 text-sky-300">
                                        Protected
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {link.download_count}
                                  {link.max_downloads && ` / ${link.max_downloads}`}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(link.expires_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(link.created_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1.5">
                                    <button
                                      onClick={() => copyShareLink(link.token)}
                                      className="p-2 rounded-lg border border-sky-500/30 bg-sky-500/10 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
                                      title="Copy link"
                                    >
                                      {copiedToken === link.token ? (
                                        <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5" />
                                      ) : (
                                        <Copy className="w-4 h-4 sm:w-5 sm:h-5" />
                                      )}
                                    </button>
                                    <button
                                      onClick={() => generateQRCode(link.token)}
                                      className="p-2 rounded-lg border border-purple-500/30 bg-purple-500/10 text-purple-200 transition hover:border-purple-500/50 hover:bg-purple-500/20"
                                      title="Generate QR Code"
                                    >
                                      <QrCode className="w-4 h-4 sm:w-5 sm:h-5" />
                                    </button>
                                    <button
                                      onClick={() => setEditingLink(link)}
                                      className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition hover:border-green-500/50 hover:bg-green-500/20"
                                      title="Edit"
                                    >
                                      <Edit className="w-4 h-4 sm:w-5 sm:h-5" />
                                    </button>
                                    <button
                                      onClick={() => handleDeleteShareLink(link.id)}
                                      className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                                      title="Delete"
                                    >
                                      <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Mobile Card View */}
                      <div className="lg:hidden space-y-3">
                        {filteredShareLinks.map((link) => (
                          <div
                            key={link.id}
                            className={`rounded-xl border border-slate-800/60 bg-slate-950/70 p-4 ${link.is_expired ? 'opacity-60' : ''}`}
                          >
                            <div className="flex items-start justify-between gap-2 mb-3">
                              <div className="min-w-0 flex-1">
                                <p className="font-semibold text-white truncate">{link.file_name}</p>
                                <p className="text-xs text-slate-400">{formatFileSize(link.file_size)}</p>
                              </div>
                              <div className="flex flex-wrap gap-1 flex-shrink-0">
                                {link.is_expired ? (
                                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold border border-red-500/40 bg-red-500/15 text-red-300">
                                    Expired
                                  </span>
                                ) : link.is_accessible ? (
                                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold border border-green-500/40 bg-green-500/15 text-green-300">
                                    Active
                                  </span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold border border-yellow-500/40 bg-yellow-500/15 text-yellow-300">
                                    Limited
                                  </span>
                                )}
                              </div>
                            </div>

                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 mb-3">
                              <span className="flex items-center gap-1">
                                <Download className="h-3 w-3" />
                                {link.download_count}{link.max_downloads && ` / ${link.max_downloads}`}
                              </span>
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                Expires: {formatDate(link.expires_at)}
                              </span>
                              {link.has_password && (
                                <span className="text-sky-400">Password protected</span>
                              )}
                            </div>

                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => copyShareLink(link.token)}
                                className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs sm:text-sm font-medium text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20 touch-manipulation active:scale-95"
                              >
                                {copiedToken === link.token ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                {copiedToken === link.token ? 'Copied!' : 'Copy'}
                              </button>
                              <button
                                onClick={() => generateQRCode(link.token)}
                                className="p-2 rounded-lg border border-purple-500/30 bg-purple-500/10 text-purple-200 transition hover:border-purple-500/50 hover:bg-purple-500/20 touch-manipulation active:scale-95"
                                title="QR Code"
                              >
                                <QrCode className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => setEditingLink(link)}
                                className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition hover:border-green-500/50 hover:bg-green-500/20 touch-manipulation active:scale-95"
                                title="Edit"
                              >
                                <Edit className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleDeleteShareLink(link.id)}
                                className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20 touch-manipulation active:scale-95"
                                title="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}

              {/* File Shares Tab */}
              {activeTab === 'shares' && (
                <>
                  {filteredFileShares.length === 0 ? (
                    <p className="text-slate-500 text-center py-8">
                      {fileShares.length === 0 ? 'No file shares yet' : 'No matching file shares found'}
                    </p>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      <div className="hidden lg:block overflow-x-auto">
                        <table className="min-w-full">
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">File</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Shared With</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Permissions</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Expires</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Actions</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60">
                            {filteredFileShares.map((share) => (
                              <tr key={share.id} className="hover:bg-slate-800/30 transition-colors">
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="font-semibold text-white">{share.file_name}</div>
                                  <div className="text-xs sm:text-sm text-slate-400 mt-0.5">
                                    {formatFileSize(share.file_size)}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{share.shared_with_username}</td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1">
                                    {share.can_read && (
                                      <span className="px-2.5 py-1 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                        Read
                                      </span>
                                    )}
                                    {share.can_write && (
                                      <span className="px-2.5 py-1 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                        Write
                                      </span>
                                    )}
                                    {share.can_delete && (
                                      <span className="px-2.5 py-1 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                        Delete
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(share.expires_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1">
                                    <button
                                      onClick={() => setEditingShare(share)}
                                      className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition hover:border-green-500/50 hover:bg-green-500/20"
                                      title="Edit permissions"
                                    >
                                      <Edit className="w-4 h-4 sm:w-5 sm:h-5" />
                                    </button>
                                    <button
                                      onClick={() => handleDeleteFileShare(share.id)}
                                      className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                                      title="Revoke"
                                    >
                                      <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Mobile Card View */}
                      <div className="lg:hidden space-y-3">
                        {filteredFileShares.map((share) => (
                          <div
                            key={share.id}
                            className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4"
                          >
                            <div className="flex items-start justify-between gap-2 mb-3">
                              <div className="min-w-0 flex-1">
                                <p className="font-semibold text-white truncate">{share.file_name}</p>
                                <p className="text-xs text-slate-400">{formatFileSize(share.file_size)}</p>
                              </div>
                              <div className="flex gap-1 flex-shrink-0">
                                <button
                                  onClick={() => setEditingShare(share)}
                                  className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition touch-manipulation active:scale-95"
                                  title="Edit"
                                >
                                  <Edit className="w-4 h-4" />
                                </button>
                                <button
                                  onClick={() => handleDeleteFileShare(share.id)}
                                  className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition touch-manipulation active:scale-95"
                                  title="Revoke"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 mb-2">
                              <Users className="h-3 w-3 text-slate-400" />
                              <span className="text-sm text-slate-300">{share.shared_with_username}</span>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              {share.can_read && (
                                <span className="px-2 py-0.5 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                  Read
                                </span>
                              )}
                              {share.can_write && (
                                <span className="px-2 py-0.5 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                  Write
                                </span>
                              )}
                              {share.can_delete && (
                                <span className="px-2 py-0.5 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                  Delete
                                </span>
                              )}
                            </div>

                            <div className="text-xs text-slate-400 flex items-center gap-1">
                              <Calendar className="h-3 w-3" />
                              Expires: {formatDate(share.expires_at)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}

              {/* Shared With Me Tab */}
              {activeTab === 'shared-with-me' && (
                <>
                  {filteredSharedWithMe.length === 0 ? (
                    <p className="text-slate-500 text-center py-8">
                      {sharedWithMe.length === 0 ? 'No files shared with you' : 'No matching shared files found'}
                    </p>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      <div className="hidden lg:block overflow-x-auto">
                        <table className="min-w-full">
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">File</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Owner</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Permissions</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Shared</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Expires</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60">
                            {filteredSharedWithMe.map((item) => (
                              <tr key={item.share_id} className="hover:bg-slate-800/30 transition-colors">
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="font-semibold text-white">{item.file_name}</div>
                                  <div className="text-xs sm:text-sm text-slate-400 mt-0.5">
                                    {formatFileSize(item.file_size)}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{item.owner_username}</td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1">
                                    {item.can_read && (
                                      <span className="px-2.5 py-1 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                        Read
                                      </span>
                                    )}
                                    {item.can_write && (
                                      <span className="px-2.5 py-1 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                        Write
                                      </span>
                                    )}
                                    {item.can_delete && (
                                      <span className="px-2.5 py-1 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                        Delete
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(item.shared_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(item.expires_at)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Mobile Card View */}
                      <div className="lg:hidden space-y-3">
                        {filteredSharedWithMe.map((item) => (
                          <div
                            key={item.share_id}
                            className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4"
                          >
                            <div className="mb-2">
                              <p className="font-semibold text-white truncate">{item.file_name}</p>
                              <p className="text-xs text-slate-400">{formatFileSize(item.file_size)}</p>
                            </div>

                            <div className="flex items-center gap-2 mb-2">
                              <Users className="h-3 w-3 text-slate-400" />
                              <span className="text-sm text-slate-300">From: {item.owner_username}</span>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              {item.can_read && (
                                <span className="px-2 py-0.5 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                  Read
                                </span>
                              )}
                              {item.can_write && (
                                <span className="px-2 py-0.5 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                  Write
                                </span>
                              )}
                              {item.can_delete && (
                                <span className="px-2 py-0.5 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                  Delete
                                </span>
                              )}
                            </div>

                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                Shared: {formatDate(item.shared_at)}
                              </span>
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                Expires: {formatDate(item.expires_at)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </>
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
          users={users}
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

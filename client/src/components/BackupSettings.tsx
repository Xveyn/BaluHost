import { useState, useEffect } from 'react';
import { Download, Trash2, RotateCcw, AlertTriangle, Database, FolderOpen, Settings, CheckCircle, XCircle, Clock, HardDrive } from 'lucide-react';
	import { listBackups, createBackup, deleteBackup, restoreBackup, downloadBackup } from '../api/backup';
	import type { Backup, BackupListResponse, CreateBackupRequest, RestoreBackupRequest } from '../api/backup';
import { apiCache } from '../lib/api';

export default function BackupSettings() {
	// Removed backupType, only checkboxes used
	const [includesDatabase, setIncludesDatabase] = useState(true);
	const [includesFiles, setIncludesFiles] = useState(true);
	const [includesConfig, setIncludesConfig] = useState(false);
	const [backupPath, setBackupPath] = useState('');
	const [backups, setBackups] = useState<Backup[]>([]);
	const [totalSize, setTotalSize] = useState({ bytes: 0, mb: 0 });
	const [loading, setLoading] = useState(true);
	const [creating, setCreating] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [success, setSuccess] = useState<string | null>(null);
	const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
	const [backupToDelete, setBackupToDelete] = useState<Backup | null>(null);
	const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
	const [selectedBackup, setSelectedBackup] = useState<Backup | null>(null);
	const [restoreConfirm, setRestoreConfirm] = useState('');
	const [deleting, setDeleting] = useState(false);
	const [restoring, setRestoring] = useState(false);

	useEffect(() => {
		loadBackups();
	}, []);

	async function loadBackups() {
		setLoading(true);
		setError(null);
		try {
			const response: BackupListResponse = await listBackups();
			setBackups(response.backups);
			const totalBytes = response.backups.reduce((acc, b) => acc + b.size_bytes, 0);
			setTotalSize({ bytes: totalBytes, mb: totalBytes / 1024 / 1024 });
		} catch (err: any) {
			setError(err.response?.data?.detail || 'Failed to load backups');
			setBackups([]);
		} finally {
			setLoading(false);
		}
	}

	async function handleCreateBackup() {
		setCreating(true);
		setError(null);
		setSuccess(null);
		try {
			const request: CreateBackupRequest = {
				includes_database: includesDatabase,
				includes_files: includesFiles,
				includes_config: includesConfig,
				backup_path: backupPath
			};
			await createBackup(request);
			setSuccess('Backup created successfully');
			// Clear API cache to force fresh backup list
			apiCache.clear();
			await loadBackups();
		} catch (err: any) {
			setError(err.response?.data?.detail || 'Failed to create backup');
		} finally {
			setCreating(false);
		}
	}

	async function handleDeleteBackup() {
		if (!backupToDelete) return;
		setDeleting(true);
		setError(null);
		try {
			await deleteBackup(backupToDelete.id);
			setSuccess('Backup deleted successfully');
			// Clear API cache to force fresh backup list
			apiCache.clear();
			await loadBackups();
			setDeleteDialogOpen(false);
			setBackupToDelete(null);
		} catch (err: any) {
			setError(err.response?.data?.detail || 'Failed to delete backup');
		} finally {
			setDeleting(false);
		}
	}

	async function handleRestoreBackup() {
		if (!selectedBackup || restoreConfirm !== 'RESTORE') return;
		setRestoring(true);
		setError(null);
		try {
			const request: RestoreBackupRequest = {
				backup_id: selectedBackup.id,
				restore_database: true,
				restore_files: true,
				restore_config: false,
				confirm: true
			};
			const response = await restoreBackup(request);
			setSuccess(response.message);
			setRestoreDialogOpen(false);
			setSelectedBackup(null);
			setRestoreConfirm('');
			setTimeout(() => {
				if (window.confirm('Backup restored. Reload the page now?')) {
					window.location.reload();
				}
			}, 2000);
		} catch (err: any) {
			setError(err.response?.data?.detail || 'Failed to restore backup');
		} finally {
			setRestoring(false);
		}
	}

	function handleDownload(backup: Backup) {
		downloadBackup(backup.id, backup.filename);
	}

	function formatDate(date: string) {
		return new Date(date).toLocaleString('de-DE', {
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function getStatusIcon(status: string) {
		switch (status) {
			case 'completed':
				return <CheckCircle className="w-5 h-5 text-emerald-500" />;
			case 'failed':
				return <XCircle className="w-5 h-5 text-red-500" />;
			case 'in_progress':
				return <Clock className="w-5 h-5 text-yellow-500 animate-spin" />;
			default:
				return null;
		}
	}

	function getStatusColor(status: string) {
		switch (status) {
			case 'completed':
				return 'text-emerald-500';
			case 'failed':
				return 'text-red-500';
			case 'in_progress':
				return 'text-yellow-500';
			default:
				return 'text-slate-400';
		}
	}

	return (
		<div className="space-y-6 w-full px-0">
			{/* Header & Formular */}
			<div className="rounded-lg shadow bg-slate-900/55 p-6 w-full">
				<div className="flex items-start justify-between">
					  <div className="w-full">
						<h2 className="text-2xl font-bold mb-2">Backup & Restore</h2>
						<p className="text-slate-400">
							Create and manage system backups. Backups include database and files.
						</p>
						<div className="mt-4 flex flex-col gap-3">
							<div className="flex flex-col gap-4 mt-2">
								{/* Removed backup type selection, only checkboxes remain */}
								<div className="flex items-center gap-6">
									<label className="flex items-center gap-2 text-sm text-slate-400">
										<input type="checkbox" checked={includesDatabase} onChange={e => setIncludesDatabase(e.target.checked)} disabled={creating} className="accent-sky-500" />
										<Database className="w-4 h-4" /> DB
									</label>
									<label className="flex items-center gap-2 text-sm text-slate-400">
										<input type="checkbox" checked={includesFiles} onChange={e => setIncludesFiles(e.target.checked)} disabled={creating} className="accent-sky-500" />
										<FolderOpen className="w-4 h-4" /> Files
									</label>
									<label className="flex items-center gap-2 text-sm text-slate-400">
										<input type="checkbox" checked={includesConfig} onChange={e => setIncludesConfig(e.target.checked)} disabled={creating} className="accent-sky-500" />
										<Settings className="w-4 h-4" /> Config
									</label>
								</div>
								<div className="flex items-center gap-2 mt-4">
									<label htmlFor="backupPath" className="text-sm text-slate-400 min-w-[120px]">Backup Location:</label>
									<input id="backupPath" type="text" value={backupPath} onChange={e => setBackupPath(e.target.value)} placeholder="e.g. /mnt/backup or leave empty" className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500 w-full" disabled={creating} />
								</div>
							</div>
							{backups && backups.length > 0 && (
								<div className="flex items-center gap-4 text-sm mt-2">
									<div className="flex items-center gap-2">
										<HardDrive className="w-4 h-4 text-slate-400" />
										<span className="text-slate-400">Total Size:</span>
										<span className="font-medium text-slate-200">{totalSize.mb.toFixed(2)} MB</span>
									</div>
									<div className="flex items-center gap-2">
										<Database className="w-4 h-4 text-slate-400" />
										<span className="text-slate-400">Backups:</span>
										<span className="font-medium text-slate-200">{backups.length}</span>
									</div>
								</div>
							)}
						</div>
					</div>
					<button onClick={handleCreateBackup} disabled={creating} className="px-4 py-2 bg-sky-500 hover:bg-sky-600 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg flex items-center gap-2 transition-colors">
						<Database className="w-4 h-4" />
						{creating ? 'Creating...' : 'Create Backup'}
					</button>
				</div>
			</div>
			{error && (
				<div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4">
					<div className="flex items-center gap-2 text-red-400">
						<AlertTriangle className="w-5 h-5" />
						<span>{error}</span>
					</div>
				</div>
			)}
			{success && (
				<div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-4">
					<div className="flex items-center gap-2 text-emerald-400">
						<CheckCircle className="w-5 h-5" />
						<span>{success}</span>
					</div>
				</div>
			)}
			<div className="rounded-lg shadow bg-slate-900/55 overflow-hidden w-full">
				<div className="p-6 border-b border-slate-800">
					<h3 className="text-lg font-semibold">Available Backups</h3>
				</div>
				{loading ? (
					<div className="p-8 text-center text-slate-400">Loading backups...</div>
				) : !backups || backups.length === 0 ? (
					<div className="p-8 text-center text-slate-400">
						<Database className="w-12 h-12 mx-auto mb-3 opacity-50" />
						<p>No backups available</p>
						<p className="text-sm mt-1">Create your first backup to get started</p>
					</div>
				) : (
					<div className="overflow-x-auto">
						<table className="w-full">
							<thead className="bg-slate-800/50">
								<tr>
									<th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Status</th>
									<th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Filename</th>
									<th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Type</th>
									<th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Size</th>
									<th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Created</th>
									<th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Contents</th>
									<th className="px-6 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Actions</th>
								</tr>
							</thead>
							<tbody className="divide-y divide-slate-800">
								{backups && backups.map((backup) => (
									<tr key={backup.id} className="hover:bg-slate-800/30 transition-colors">
										<td className="px-6 py-4 whitespace-nowrap">
											<div className="flex items-center gap-2">
												{getStatusIcon(backup.status)}
												<span className={`text-sm font-medium ${getStatusColor(backup.status)}`}>{backup.status}</span>
											</div>
										</td>
										<td className="px-6 py-4">
											<div className="text-sm font-medium text-slate-200">{backup.filename}</div>
											{backup.error_message && (
												<div className="text-xs text-red-400 mt-1">{backup.error_message}</div>
											)}
										</td>
										<td className="px-6 py-4 whitespace-nowrap">
											<span className="px-2 py-1 text-xs font-medium rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20">{backup.backup_type}</span>
										</td>
										<td className="px-6 py-4 whitespace-nowrap text-sm text-slate-300">{backup.size_mb.toFixed(2)} MB</td>
										<td className="px-6 py-4 whitespace-nowrap text-sm text-slate-400">{formatDate(backup.created_at)}</td>
										<td className="px-6 py-4">
											<div className="flex items-center gap-2 text-xs">
												{backup.includes_database && (<span className="flex items-center gap-1 text-slate-400"><Database className="w-3 h-3" />DB</span>)}
												{backup.includes_files && (<span className="flex items-center gap-1 text-slate-400"><FolderOpen className="w-3 h-3" />Files</span>)}
												{backup.includes_config && (<span className="flex items-center gap-1 text-slate-400"><Settings className="w-3 h-3" />Config</span>)}
											</div>
										</td>
										<td className="px-6 py-4 whitespace-nowrap text-right text-sm">
											<div className="flex items-center justify-end gap-2">
												{backup.status === 'completed' && (
													<>
														<button onClick={() => handleDownload(backup)} className="p-2 text-slate-400 hover:text-sky-400 hover:bg-slate-800 rounded-lg transition-colors" title="Download">
															<Download className="w-4 h-4" />
														</button>
														<button onClick={() => { setSelectedBackup(backup); setRestoreDialogOpen(true); }} className="p-2 text-slate-400 hover:text-emerald-400 hover:bg-slate-800 rounded-lg transition-colors" title="Restore">
															<RotateCcw className="w-4 h-4" />
														</button>
													</>
												)}
												<button onClick={() => { setBackupToDelete(backup); setDeleteDialogOpen(true); }} className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-800 rounded-lg transition-colors" title="Delete">
													<Trash2 className="w-4 h-4" />
												</button>
											</div>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
			{deleteDialogOpen && backupToDelete && (
				<div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
					<div className="bg-slate-900 rounded-lg shadow-xl max-w-md w-full p-6 border border-slate-800">
						<div className="flex items-start gap-4 mb-4">
							<div className="p-3 bg-red-500/10 rounded-full">
								<AlertTriangle className="w-6 h-6 text-red-400" />
							</div>
							<div className="flex-1">
								<h3 className="text-lg font-semibold text-slate-100 mb-2">Delete Backup</h3>
								<p className="text-sm text-slate-400">Are you sure you want to delete <span className="font-medium text-slate-200">{backupToDelete.filename}</span>? This action cannot be undone.</p>
							</div>
						</div>
						<div className="flex justify-end gap-3">
							<button onClick={() => { setDeleteDialogOpen(false); setBackupToDelete(null); }} disabled={deleting} className="px-4 py-2 text-slate-300 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-colors">Cancel</button>
							<button onClick={handleDeleteBackup} disabled={deleting} className="px-4 py-2 bg-red-500 hover:bg-red-600 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors">{deleting ? 'Deleting...' : 'Delete'}</button>
						</div>
					</div>
				</div>
			)}
			{restoreDialogOpen && selectedBackup && (
				<div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
					<div className="bg-slate-900 rounded-lg shadow-xl max-w-md w-full p-6 border border-slate-800">
						<div className="flex items-start gap-4 mb-4">
							<div className="p-3 bg-yellow-500/10 rounded-full">
								<AlertTriangle className="w-6 h-6 text-yellow-400" />
							</div>
							<div className="flex-1">
								<h3 className="text-lg font-semibold text-slate-100 mb-2">Restore Backup</h3>
								<p className="text-sm text-slate-400 mb-4">⚠️ This will <strong className="text-red-400">overwrite all current data</strong> with the backup from:</p>
								<div className="p-3 bg-slate-800 rounded-lg mb-4">
									<div className="text-sm text-slate-300 font-medium">{selectedBackup.filename}</div>
									<div className="text-xs text-slate-400 mt-1">{formatDate(selectedBackup.created_at)}</div>
								</div>
								<p className="text-sm text-slate-400 mb-4">Type <span className="font-mono font-bold text-red-400">RESTORE</span> to confirm:</p>
								<input type="text" value={restoreConfirm} onChange={(e) => setRestoreConfirm(e.target.value)} placeholder="Type RESTORE" className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500" disabled={restoring} />
							</div>
						</div>
						<div className="flex justify-end gap-3">
							<button onClick={() => { setRestoreDialogOpen(false); setSelectedBackup(null); setRestoreConfirm(''); }} disabled={restoring} className="px-4 py-2 text-slate-300 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-colors">Cancel</button>
							<button onClick={handleRestoreBackup} disabled={restoring || restoreConfirm !== 'RESTORE'} className="px-4 py-2 bg-yellow-500 hover:bg-yellow-600 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors">{restoring ? 'Restoring...' : 'Restore Backup'}</button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}

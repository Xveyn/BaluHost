/**
 * FileViewer component -- displays file previews in a modal overlay.
 *
 * Supports images, video, audio, PDF, and plain-text files.
 */

import { useState, useEffect } from 'react';
import { buildApiUrl } from '../../lib/api';
import {
  getFileExtension,
  isTextFile,
  isImageFile,
  isVideoFile,
  isAudioFile,
  isPdfFile,
} from '../../lib/fileTypes';
import type { FileItem } from './types';

interface FileViewerProps {
  file: FileItem;
  onClose: () => void;
}

export function FileViewer({ file, onClose }: FileViewerProps) {
  const [content, setContent] = useState<string>('');
  const [blobUrl, setBlobUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    loadFileContent();

    // Cleanup blob URL when component unmounts
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.path]);

  const loadFileContent = async () => {
    setLoading(true);
    setError('');
    const token = localStorage.getItem('token');
    if (!token) {
      setError('Not authenticated');
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl(`/api/files/download/${encodeURIComponent(file.path)}`), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const blob = await response.blob();

        // For images, videos, audio, PDFs - create blob URL
        if (isImageFile(file.name) || isVideoFile(file.name) || isAudioFile(file.name) || isPdfFile(file.name)) {
          const url = URL.createObjectURL(blob);
          setBlobUrl(url);
        } else {
          // For text files - convert to text
          const text = await blob.text();
          setContent(text);
        }
      } else {
        setError('Failed to load file');
      }
    } catch (err) {
      console.error('Failed to load file:', err);
      setError('Failed to load file');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-lg p-2 sm:p-4">
      <div className="card w-full max-w-4xl max-h-[95vh] sm:max-h-[90vh] border-slate-800/60 bg-slate-900/90 flex flex-col">
        <div className="flex items-start sm:items-center justify-between gap-3 mb-3 sm:mb-4">
          <div className="min-w-0 flex-1">
            <h3 className="text-lg sm:text-xl font-semibold text-white truncate">{file.name}</h3>
            <p className="text-xs sm:text-sm text-slate-400 mt-1 truncate">{file.path}</p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-xl border border-slate-700/70 bg-slate-900/70 px-3 sm:px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white touch-manipulation active:scale-95"
          >
            <span className="hidden sm:inline">✕ Close</span>
            <span className="sm:hidden">✕</span>
          </button>
        </div>
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-slate-500">Loading file...</p>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-rose-400">{error}</p>
            </div>
          ) : isImageFile(file.name) ? (
            <div className="flex items-center justify-center p-4 bg-slate-950/50">
              <img
                src={blobUrl}
                alt={file.name}
                className="max-w-full max-h-[70vh] rounded-lg"
              />
            </div>
          ) : isVideoFile(file.name) ? (
            <div className="p-4">
              <video controls className="w-full max-h-[70vh] rounded-lg bg-black">
                <source src={blobUrl} type={`video/${getFileExtension(file.name)}`} />
                Your browser does not support the video tag.
              </video>
            </div>
          ) : isAudioFile(file.name) ? (
            <div className="flex flex-col items-center justify-center p-8">
              <div className="mb-4 text-6xl">🎵</div>
              <audio controls className="w-full max-w-md">
                <source src={blobUrl} type={`audio/${getFileExtension(file.name)}`} />
                Your browser does not support the audio tag.
              </audio>
            </div>
          ) : isPdfFile(file.name) ? (
            <div className="p-4">
              <iframe
                src={blobUrl}
                className="w-full h-[70vh] rounded-lg border border-slate-800"
                title={file.name}
              />
            </div>
          ) : isTextFile(file.name) ? (
            <pre className="p-4 text-sm text-slate-300 font-mono whitespace-pre-wrap break-words bg-slate-950/50 rounded-lg">
              {content}
            </pre>
          ) : (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-slate-500">Preview not available for this file type</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

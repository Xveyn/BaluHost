import { describe, it, expect } from 'vitest';
import {
  getFileExtension,
  isTextFile,
  isImageFile,
  isVideoFile,
  isAudioFile,
  isPdfFile,
} from '../../lib/fileTypes';

describe('getFileExtension', () => {
  it('returns lowercase extension', () => {
    expect(getFileExtension('photo.JPG')).toBe('jpg');
    expect(getFileExtension('doc.PDF')).toBe('pdf');
  });

  it('returns last extension for multiple dots', () => {
    expect(getFileExtension('archive.tar.gz')).toBe('gz');
  });

  it('returns empty string for no extension', () => {
    expect(getFileExtension('Makefile')).toBe('makefile');
  });

  it('returns empty string for empty filename', () => {
    expect(getFileExtension('')).toBe('');
  });
});

describe('isTextFile', () => {
  it('recognizes common text extensions', () => {
    expect(isTextFile('readme.md')).toBe(true);
    expect(isTextFile('config.json')).toBe(true);
    expect(isTextFile('app.tsx')).toBe(true);
    expect(isTextFile('main.py')).toBe(true);
    expect(isTextFile('notes.txt')).toBe(true);
    expect(isTextFile('script.sh')).toBe(true);
  });

  it('rejects non-text files', () => {
    expect(isTextFile('photo.png')).toBe(false);
    expect(isTextFile('video.mp4')).toBe(false);
    expect(isTextFile('document.pdf')).toBe(false);
  });
});

describe('isImageFile', () => {
  it('recognizes image extensions', () => {
    expect(isImageFile('photo.jpg')).toBe(true);
    expect(isImageFile('photo.jpeg')).toBe(true);
    expect(isImageFile('icon.png')).toBe(true);
    expect(isImageFile('animation.gif')).toBe(true);
    expect(isImageFile('logo.svg')).toBe(true);
    expect(isImageFile('image.webp')).toBe(true);
  });

  it('rejects non-image files', () => {
    expect(isImageFile('doc.pdf')).toBe(false);
    expect(isImageFile('video.mp4')).toBe(false);
  });
});

describe('isVideoFile', () => {
  it('recognizes video extensions', () => {
    expect(isVideoFile('clip.mp4')).toBe(true);
    expect(isVideoFile('movie.webm')).toBe(true);
    expect(isVideoFile('rec.mov')).toBe(true);
  });

  it('rejects non-video files', () => {
    expect(isVideoFile('song.mp3')).toBe(false);
    expect(isVideoFile('photo.jpg')).toBe(false);
  });
});

describe('isAudioFile', () => {
  it('recognizes audio extensions', () => {
    expect(isAudioFile('song.mp3')).toBe(true);
    expect(isAudioFile('track.flac')).toBe(true);
    expect(isAudioFile('sound.wav')).toBe(true);
    expect(isAudioFile('music.m4a')).toBe(true);
  });

  it('rejects non-audio files', () => {
    expect(isAudioFile('video.mp4')).toBe(false);
    expect(isAudioFile('photo.png')).toBe(false);
  });
});

describe('isPdfFile', () => {
  it('recognizes pdf', () => {
    expect(isPdfFile('document.pdf')).toBe(true);
    expect(isPdfFile('REPORT.PDF')).toBe(true);
  });

  it('rejects non-pdf', () => {
    expect(isPdfFile('document.docx')).toBe(false);
  });
});

import { describe, it, expect } from 'vitest';
import { formatDate, formatFileSize, getProviderLabel } from '../../../components/shares/sharesFormat';
import type { CloudExportJob } from '../../../api/cloud-export';

const job = (share_link: string | null): CloudExportJob =>
  ({ share_link } as CloudExportJob);

describe('sharesFormat', () => {
  it('formatDate returns the never-label for null', () => {
    expect(formatDate(null, 'NEVER')).toBe('NEVER');
  });

  it('formatDate renders a real date via toLocaleDateString', () => {
    expect(formatDate('2026-01-15T00:00:00Z', 'NEVER'))
      .toBe(new Date('2026-01-15T00:00:00Z').toLocaleDateString());
  });

  it('formatFileSize returns 0 B for null/zero', () => {
    expect(formatFileSize(null)).toBe('0 B');
    expect(formatFileSize(0)).toBe('0 B');
  });

  it('getProviderLabel maps known hosts', () => {
    expect(getProviderLabel(job('https://drive.google.com/x'))).toBe('Google Drive');
    expect(getProviderLabel(job('https://1drv.ms/x'))).toBe('OneDrive');
    expect(getProviderLabel(job('https://acme.sharepoint.com/x'))).toBe('OneDrive');
    expect(getProviderLabel(job('https://example.com/x'))).toBe('Cloud');
    expect(getProviderLabel(job(null))).toBe('Cloud');
  });
});

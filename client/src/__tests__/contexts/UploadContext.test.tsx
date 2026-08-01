/**
 * The upload queue — the NAS's core interaction, and the last big untested
 * area from T3/#317 besides the notification socket.
 *
 * What is worth pinning down here is not the happy path (a POST goes out) but
 * the decisions the context makes BEFORE anything is sent: does it ask about
 * duplicates, does it respect a "skip", does the rename land where a user
 * expects it, and does it refuse an upload that cannot fit.
 *
 * Runs on renderWithProviders (T2/#316): real providers, real i18n, one route
 * table for both transports — the batch upload uses raw `fetch`, the duplicate
 * check goes through axios.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import { renderWithProviders } from '../helpers/renderWithProviders';
import { useAuth } from '../../contexts/AuthContext';
import { useUpload, type DuplicateDecision } from '../../contexts/UploadContext';

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

const CHECK = '/api/files/check-exists';
const UPLOAD = '/api/files/upload';

function file(name: string, size = 10): File {
  return new File([new Uint8Array(size)], name);
}

/** FileList is not constructible in jsdom; the context only does Array.from(). */
function asFileList(files: File[]): FileList {
  return { ...files, length: files.length, item: (i: number) => files[i] } as unknown as FileList;
}

function Harness({
  files,
  availableBytes,
  decisions = [],
}: {
  files: File[];
  availableBytes?: number | null;
  decisions?: DuplicateDecision[];
}) {
  const { startUpload, uploads, pendingUpload, handleDuplicateResolution } = useUpload();
  // UploadProvider reads its token from AuthContext and silently returns
  // without one, so every test has to wait for the sign-in to land first -
  // exactly like a user who cannot click before the app has loaded.
  const { token } = useAuth();
  return (
    <div>
      <p data-testid="auth">{token ? 'angemeldet' : 'lädt'}</p>
      <button onClick={() => startUpload(asFileList(files), '/Shared', availableBytes)}>hochladen</button>
      <button onClick={() => handleDuplicateResolution(decisions)}>entscheiden</button>
      <p data-testid="pending">{pendingUpload ? 'dialog' : 'kein-dialog'}</p>
      <p data-testid="queue">{uploads.size}</p>
    </div>
  );
}

async function setup(props: React.ComponentProps<typeof Harness>, routes: Record<string, unknown>) {
  const rendered = renderWithProviders(<Harness {...props} />, {
    auth: { username: 'sven' },
    withUpload: true,
    api: { [CHECK]: { duplicates: [] }, [UPLOAD]: { uploaded: [] }, ...routes },
  });
  await screen.findByText('angemeldet');
  return rendered;
}

/** The names the app actually put into the multipart body. */
function uploadedNames(body: unknown): string[] {
  return (body as FormData).getAll('files').map((f) => (f as File).name);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the duplicate gate', () => {
  it('uploads straight away when nothing collides', async () => {
    const { user, api } = await setup({ files: [file('neu.txt')] }, {});

    await user.click(screen.getByRole('button', { name: 'hochladen' }));

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
    expect(screen.getByTestId('pending')).toHaveTextContent('kein-dialog');
  });

  it('asks first and sends nothing while the question is open', async () => {
    const { user, api } = await setup(
      { files: [file('bericht.pdf')] },
      { [CHECK]: { duplicates: [{ filename: 'bericht.pdf', size_bytes: 10, modified_at: '', checksum: null }] } },
    );

    await user.click(screen.getByRole('button', { name: 'hochladen' }));

    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('dialog'));
    expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(0);
  });

  it('uploads anyway when the duplicate check itself fails', async () => {
    // Deliberate: a broken check must not block the upload. Documented here so
    // the fallback is a decision, not an accident.
    const { user, api } = await setup(
      { files: [file('neu.txt')] },
      { [CHECK]: { status: 500, body: { detail: 'boom' } } },
    );

    await user.click(screen.getByRole('button', { name: 'hochladen' }));

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
  });
});

describe('what the user decides in the dialog', () => {
  const collide = (name: string) => ({
    [CHECK]: { duplicates: [{ filename: name, size_bytes: 10, modified_at: '', checksum: null }] },
  });

  async function openDialogAndDecide(
    files: File[],
    decisions: DuplicateDecision[],
    duplicateName: string,
  ) {
    const rendered = await setup({ files, decisions }, collide(duplicateName));
    await rendered.user.click(screen.getByRole('button', { name: 'hochladen' }));
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('dialog'));
    await rendered.user.click(screen.getByRole('button', { name: 'entscheiden' }));
    return rendered;
  }

  it('skip really skips — no request at all when it was the only file', async () => {
    const { api } = await openDialogAndDecide(
      [file('bericht.pdf')],
      [{ filename: 'bericht.pdf', resolution: 'skip' }],
      'bericht.pdf',
    );

    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('kein-dialog'));
    expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(0);
  });

  it('keep-both renames before the extension, not after it', async () => {
    const { api } = await openDialogAndDecide(
      [file('bericht.pdf')],
      [{ filename: 'bericht.pdf', resolution: 'keep-both' }],
      'bericht.pdf',
    );

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
    expect(uploadedNames(api.callsTo(UPLOAD, 'POST')[0].body)).toEqual(['bericht (1).pdf']);
  });

  it('keep-both appends when there is no extension', async () => {
    const { api } = await openDialogAndDecide(
      [file('README')],
      [{ filename: 'README', resolution: 'keep-both' }],
      'README',
    );

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
    expect(uploadedNames(api.callsTo(UPLOAD, 'POST')[0].body)).toEqual(['README (1)']);
  });

  it('overwrite keeps the original name', async () => {
    const { api } = await openDialogAndDecide(
      [file('bericht.pdf')],
      [{ filename: 'bericht.pdf', resolution: 'overwrite' }],
      'bericht.pdf',
    );

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
    expect(uploadedNames(api.callsTo(UPLOAD, 'POST')[0].body)).toEqual(['bericht.pdf']);
  });

  it('carries the non-colliding files along untouched', async () => {
    const { api } = await openDialogAndDecide(
      [file('bericht.pdf'), file('anderes.txt')],
      [{ filename: 'bericht.pdf', resolution: 'skip' }],
      'bericht.pdf',
    );

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
    expect(uploadedNames(api.callsTo(UPLOAD, 'POST')[0].body)).toEqual(['anderes.txt']);
  });
});

describe('capacity', () => {
  it('refuses an upload that does not fit and sends nothing', async () => {
    const { user, api } = await setup({ files: [file('gross.bin', 500)], availableBytes: 100 }, {});

    await user.click(screen.getByRole('button', { name: 'hochladen' }));

    await waitFor(() => expect(api.callsTo(CHECK, 'POST')).toHaveLength(1));
    expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(0);
  });

  it('proceeds when the free space is unknown', async () => {
    const { user, api } = await setup({ files: [file('gross.bin', 500)], availableBytes: null }, {});

    await user.click(screen.getByRole('button', { name: 'hochladen' }));

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
  });
});

describe('batching', () => {
  it('splits at 50 files per request', async () => {
    const files = Array.from({ length: 51 }, (_, i) => file(`datei-${i}.txt`));
    const { user, api } = await setup({ files }, {});

    await user.click(screen.getByRole('button', { name: 'hochladen' }));

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(2));
    const [first, second] = api.callsTo(UPLOAD, 'POST');
    expect(uploadedNames(first.body)).toHaveLength(50);
    expect(uploadedNames(second.body)).toHaveLength(1);
  });

  it('sends the target path with every batch', async () => {
    const { user, api } = await setup({ files: [file('a.txt')] }, {});

    await user.click(screen.getByRole('button', { name: 'hochladen' }));

    await waitFor(() => expect(api.callsTo(UPLOAD, 'POST')).toHaveLength(1));
    expect((api.callsTo(UPLOAD, 'POST')[0].body as FormData).get('path')).toBe('/Shared');
  });
});

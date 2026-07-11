import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FileNameCell } from '../../../components/shares/FileNameCell';

describe('FileNameCell', () => {
  it('shows the folder label for a directory', () => {
    render(<FileNameCell isDirectory name="Docs" folderLabel="FOLDER" />);
    expect(screen.getByText('Docs')).toBeInTheDocument();
    expect(screen.getByText('FOLDER')).toBeInTheDocument();
  });

  it('shows a formatted size for a file', () => {
    render(<FileNameCell isDirectory={false} name="a.txt" size={0} folderLabel="FOLDER" />);
    expect(screen.getByText('a.txt')).toBeInTheDocument();
    expect(screen.getByText('0 B')).toBeInTheDocument();
    expect(screen.queryByText('FOLDER')).toBeNull();
  });

  it('renders in card variant without crashing', () => {
    render(<FileNameCell isDirectory={false} name="b.txt" size={0} folderLabel="F" variant="card" />);
    expect(screen.getByText('b.txt')).toBeInTheDocument();
  });
});

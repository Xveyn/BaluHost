import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    open: true,
    message: 'Are you sure?',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  it('renders nothing when open=false', () => {
    const { container } = render(
      <ConfirmDialog {...defaultProps} open={false} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders title, message, and buttons when open=true', () => {
    render(<ConfirmDialog {...defaultProps} />);

    // "Confirm" appears as both title (h3) and button — use getAllByText
    expect(screen.getAllByText('Confirm')).toHaveLength(2);
    expect(screen.getByText('Are you sure?')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('uses default title "Confirm"', () => {
    render(<ConfirmDialog {...defaultProps} />);
    // Title is in an h3 element
    const heading = screen.getByRole('heading', { level: 3 });
    expect(heading).toHaveTextContent('Confirm');
  });

  it('calls onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog {...defaultProps} onConfirm={onConfirm} confirmLabel="OK" />
    );

    fireEvent.click(screen.getByText('OK'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('calls onCancel when Escape key is pressed', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('renders danger variant with rose styling', () => {
    const { container } = render(
      <ConfirmDialog {...defaultProps} variant="danger" />
    );
    const card = container.querySelector('.border-rose-500\\/40');
    expect(card).not.toBeNull();
  });

  it('renders warning variant with amber styling', () => {
    const { container } = render(
      <ConfirmDialog {...defaultProps} variant="warning" />
    );
    const card = container.querySelector('.border-amber-500\\/40');
    expect(card).not.toBeNull();
  });

  it('shows custom labels', () => {
    render(
      <ConfirmDialog
        {...defaultProps}
        title="Delete file?"
        confirmLabel="Yes, delete"
        cancelLabel="Keep it"
      />
    );

    expect(screen.getByText('Delete file?')).toBeInTheDocument();
    expect(screen.getByText('Yes, delete')).toBeInTheDocument();
    expect(screen.getByText('Keep it')).toBeInTheDocument();
  });
});

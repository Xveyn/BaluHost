import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { Modal } from '../../../components/ui/Modal';

describe('Modal close-suppression props', () => {
  it('closes on overlay click by default', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="X">body</Modal>
    );
    // Modal is rendered via createPortal into document.body, so search the full DOM
    const backdrop = document.querySelector('.bg-black\\/50') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not close on overlay click when closeOnOverlayClick=false', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="X" closeOnOverlayClick={false}>body</Modal>
    );
    // Modal is rendered via createPortal into document.body, so search the full DOM
    const backdrop = document.querySelector('.bg-black\\/50') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes on Escape by default', () => {
    const onClose = vi.fn();
    render(<Modal isOpen onClose={onClose} title="X">body</Modal>);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not close on Escape when closeOnEscape=false', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="X" closeOnEscape={false}>body</Modal>
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});

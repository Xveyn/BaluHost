import '@testing-library/jest-dom/vitest';

// Mock i18n module - formatters.ts imports i18n for locale detection
vi.mock('../i18n', () => ({
  default: { language: 'de' },
}));

// Mock matchMedia (used by various UI components)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver (used by Recharts components and @dnd-kit, which calls
// `new ResizeObserver(...)`). Must be a real constructor: in Vitest 4 a
// `vi.fn()` with an arrow-function implementation is not constructable.
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

import '@testing-library/jest-dom/vitest';
import '@shared/i18n/i18n';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  configurable: true,
  value: ResizeObserverMock,
});

Object.defineProperty(window.HTMLElement.prototype, 'offsetHeight', {
  configurable: true,
  value: 48,
});

Object.defineProperty(window.HTMLElement.prototype, 'offsetWidth', {
  configurable: true,
  value: 320,
});

Object.defineProperty(window.HTMLElement.prototype, 'scrollHeight', {
  configurable: true,
  value: 48,
});

Object.defineProperty(window.HTMLElement.prototype, 'scrollWidth', {
  configurable: true,
  value: 320,
});

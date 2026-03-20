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

Object.defineProperty(window.HTMLElement.prototype, 'clientHeight', {
  configurable: true,
  value: 48,
});

Object.defineProperty(window.HTMLElement.prototype, 'clientWidth', {
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

Object.defineProperty(window.HTMLElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  value() {
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 48,
      right: 320,
      width: 320,
      height: 48,
      toJSON() {
        return {};
      },
    };
  },
});

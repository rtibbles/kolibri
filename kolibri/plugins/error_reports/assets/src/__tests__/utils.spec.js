import {
  VueErrorReport,
  JavascriptErrorReport,
  UnhandledRejectionErrorReport,
  getWindowBreakpoint,
} from '../utils';

// Mock dependencies
jest.mock('kolibri/utils/browserInfo', () => ({
  browser: { name: 'Chrome', major: '100', minor: '0', patch: '0' },
  os: { name: 'Windows', major: '10' },
  device: { type: 'desktop', model: null, vendor: null },
  isTouchDevice: false,
}));

jest.mock('kolibri/router', () => ({
  __esModule: true,
  default: {
    currentRoute: {
      name: 'TestRoute',
      path: '/test',
      fullPath: '/test?param=1',
      params: { id: '123' },
      query: { param: '1' },
    },
  },
}));

jest.mock('../breadcrumbs', () => ({
  getBreadcrumbs: jest.fn(() => [
    { type: 'ui', category: 'click', data: { element: 'button' }, timestamp: 1000 },
    { type: 'navigation', category: 'route', data: { to: '/test' }, timestamp: 2000 },
  ]),
}));

jest.mock('../errorQueue', () => ({
  report: jest.fn(data => Promise.resolve({ queued: true, deduplicated: false, count: 1 })),
}));

describe('utils', () => {
  describe('getWindowBreakpoint', () => {
    it('should return correct breakpoint for small screens', () => {
      expect(getWindowBreakpoint(400)).toBe(480);
    });

    it('should return correct breakpoint for medium screens', () => {
      expect(getWindowBreakpoint(700)).toBe(840);
    });

    it('should return correct breakpoint for large screens', () => {
      expect(getWindowBreakpoint(1200)).toBe(1280 - 16);
    });

    it('should return max breakpoint for very large screens', () => {
      expect(getWindowBreakpoint(2000)).toBe(1600 - 16);
    });

    it('should use window.innerWidth by default', () => {
      const originalInnerWidth = window.innerWidth;
      Object.defineProperty(window, 'innerWidth', { value: 500, writable: true });

      expect(getWindowBreakpoint()).toBe(600);

      Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, writable: true });
    });
  });

  describe('ErrorReport base context', () => {
    it('should include browser info in context', () => {
      const error = new Error('Test error');
      const report = new JavascriptErrorReport({ error });
      const context = report.getErrorReport().context;

      expect(context.browser).toEqual({
        name: 'Chrome',
        major: '100',
        minor: '0',
        patch: '0',
      });
    });

    it('should include OS info in context', () => {
      const error = new Error('Test error');
      const report = new JavascriptErrorReport({ error });
      const context = report.getErrorReport().context;

      expect(context.os).toEqual({
        name: 'Windows',
        major: '10',
      });
    });

    it('should include device info in context', () => {
      const error = new Error('Test error');
      const report = new JavascriptErrorReport({ error });
      const context = report.getErrorReport().context;

      expect(context.device).toMatchObject({
        type: 'desktop',
        is_touch_device: false,
      });
      expect(context.device.screen_breakpoint).toBeDefined();
    });

    it('should include route context', () => {
      const error = new Error('Test error');
      const report = new JavascriptErrorReport({ error });
      const context = report.getErrorReport().context;

      expect(context.route).toEqual({
        name: 'TestRoute',
        path: '/test',
        params: { id: '123' },
      });
    });

    it('should include page context', () => {
      const error = new Error('Test error');
      const report = new JavascriptErrorReport({ error });
      const context = report.getErrorReport().context;

      expect(context.page).toBeDefined();
      expect(context.page.url).toBeDefined();
      expect(context.page.visible).toBeDefined();
    });

    it('should include breadcrumbs', () => {
      const error = new Error('Test error');
      const report = new JavascriptErrorReport({ error });
      const context = report.getErrorReport().context;

      expect(context.breadcrumbs).toBeDefined();
      expect(context.breadcrumbs.length).toBe(2);
    });
  });

  describe('VueErrorReport', () => {
    // Helper to create mock vm with explicit control over undefined values
    const createMockVm = (overrides = {}) => {
      const vm = {
        $options: {
          name: 'name' in overrides ? overrides.name : 'TestComponent',
          _componentTag: '_componentTag' in overrides ? overrides._componentTag : undefined,
        },
        $parent: '$parent' in overrides ? overrides.$parent : null,
        $props: '$props' in overrides ? overrides.$props : { propA: 'value', propB: 123 },
      };
      return vm;
    };

    it('should capture component name from $options.name', () => {
      const error = new Error('Vue error');
      const vm = createMockVm({ name: 'MyComponent' });
      const report = new VueErrorReport(error, vm);
      const context = report.getErrorReport().context;

      expect(context.component.name).toBe('MyComponent');
    });

    it('should fall back to _componentTag when name is not available', () => {
      const error = new Error('Vue error');
      const vm = createMockVm({ name: undefined, _componentTag: 'my-component' });
      const report = new VueErrorReport(error, vm);
      const context = report.getErrorReport().context;

      expect(context.component.name).toBe('my-component');
    });

    it('should use "Unknown Component" when no name available', () => {
      const error = new Error('Vue error');
      const vm = createMockVm({ name: undefined, _componentTag: undefined });
      const report = new VueErrorReport(error, vm);
      const context = report.getErrorReport().context;

      expect(context.component.name).toBe('Unknown Component');
    });

    it('should capture parent component chain', () => {
      const error = new Error('Vue error');
      const grandparent = createMockVm({ name: 'GrandParent' });
      const parent = createMockVm({ name: 'Parent', $parent: grandparent });
      const vm = createMockVm({ name: 'Child', $parent: parent });

      const report = new VueErrorReport(error, vm);
      const context = report.getErrorReport().context;

      expect(context.component.parents).toEqual(['Parent', 'GrandParent']);
    });

    it('should limit parent chain to 5 levels', () => {
      const error = new Error('Vue error');

      // Create a deep parent chain
      let current = createMockVm({ name: 'Level0' });
      for (let i = 1; i <= 10; i++) {
        current = createMockVm({ name: `Level${i}`, $parent: current });
      }

      const report = new VueErrorReport(error, current);
      const context = report.getErrorReport().context;

      expect(context.component.parents.length).toBe(5);
    });

    it('should sanitize props - exclude functions', () => {
      const error = new Error('Vue error');
      const vm = createMockVm({
        $props: {
          stringProp: 'value',
          funcProp: () => {},
        },
      });

      const report = new VueErrorReport(error, vm);
      const context = report.getErrorReport().context;

      expect(context.component.props.stringProp).toBe('value');
      expect(context.component.props.funcProp).toBeUndefined();
    });

    it('should sanitize props - replace objects with placeholder', () => {
      const error = new Error('Vue error');
      const vm = createMockVm({
        $props: {
          stringProp: 'value',
          objectProp: { nested: 'data' },
          arrayProp: [1, 2, 3],
        },
      });

      const report = new VueErrorReport(error, vm);
      const context = report.getErrorReport().context;

      expect(context.component.props.stringProp).toBe('value');
      expect(context.component.props.objectProp).toBe('[Object]');
      expect(context.component.props.arrayProp).toBe('[Object]');
    });

    it('should handle null props', () => {
      const error = new Error('Vue error');
      const vm = createMockVm({ $props: null });

      const report = new VueErrorReport(error, vm);
      const context = report.getErrorReport().context;

      expect(context.component.props).toEqual({});
    });
  });

  describe('JavascriptErrorReport', () => {
    it('should extract message from error event', () => {
      const errorEvent = {
        error: new Error('JS runtime error'),
        message: 'fallback message',
      };

      const report = new JavascriptErrorReport(errorEvent);
      const data = report.getErrorReport();

      expect(data.error_message).toBe('JS runtime error');
    });

    it('should fall back to event message when error object is missing', () => {
      const errorEvent = {
        error: null,
        message: 'Script error',
      };

      const report = new JavascriptErrorReport(errorEvent);
      const data = report.getErrorReport();

      expect(data.error_message).toBe('Script error');
    });

    it('should capture stack trace', () => {
      const error = new Error('Test error');
      const report = new JavascriptErrorReport({ error });
      const data = report.getErrorReport();

      expect(data.traceback).toContain('Error: Test error');
    });
  });

  describe('UnhandledRejectionErrorReport', () => {
    it('should extract message from rejection reason', () => {
      const event = {
        reason: new Error('Promise rejected'),
      };

      const report = new UnhandledRejectionErrorReport(event);
      const data = report.getErrorReport();

      expect(data.error_message).toBe('Promise rejected');
    });

    it('should handle string rejection reasons', () => {
      const event = {
        reason: 'Simple string rejection',
      };

      const report = new UnhandledRejectionErrorReport(event);
      const data = report.getErrorReport();

      // String reason won't have .message, so it uses fallback
      expect(data.error_message).toBeDefined();
    });

    it('should handle undefined rejection reasons', () => {
      const event = {
        reason: undefined,
      };

      const report = new UnhandledRejectionErrorReport(event);
      const data = report.getErrorReport();

      expect(data.error_message).toBe('Unknown Error');
    });
  });
});

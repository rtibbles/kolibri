import {
  getBreadcrumbs,
  addBreadcrumb,
  initBreadcrumbs,
  clearBreadcrumbs,
  _resetInitialized,
  _resetWrappers,
} from '../breadcrumbs';

describe('breadcrumbs', () => {
  beforeEach(() => {
    clearBreadcrumbs();
    _resetInitialized();
    jest.clearAllMocks();
  });

  describe('addBreadcrumb', () => {
    it('should add a breadcrumb with correct structure', () => {
      addBreadcrumb('ui', 'click', { element: 'button' });

      const breadcrumbs = getBreadcrumbs();
      expect(breadcrumbs.length).toBe(1);
      expect(breadcrumbs[0]).toMatchObject({
        type: 'ui',
        category: 'click',
        data: { element: 'button' },
      });
      expect(breadcrumbs[0].timestamp).toBeDefined();
      expect(typeof breadcrumbs[0].timestamp).toBe('number');
    });

    it('should add breadcrumbs in order', () => {
      addBreadcrumb('ui', 'click', { element: 'button1' });
      addBreadcrumb('navigation', 'route', { to: '/page2' });
      addBreadcrumb('http', 'fetch', { url: '/api/data' });

      const breadcrumbs = getBreadcrumbs();
      expect(breadcrumbs.length).toBe(3);
      expect(breadcrumbs[0].category).toBe('click');
      expect(breadcrumbs[1].category).toBe('route');
      expect(breadcrumbs[2].category).toBe('fetch');
    });

    it('should limit breadcrumbs to MAX_BREADCRUMBS', () => {
      // Add more than the max (30)
      for (let i = 0; i < 40; i++) {
        addBreadcrumb('test', 'item', { index: i });
      }

      const breadcrumbs = getBreadcrumbs();
      expect(breadcrumbs.length).toBe(30);
    });

    it('should drop oldest breadcrumbs when limit is exceeded', () => {
      for (let i = 0; i < 35; i++) {
        addBreadcrumb('test', 'item', { index: i });
      }

      const breadcrumbs = getBreadcrumbs();
      // First 5 should be dropped
      expect(breadcrumbs[0].data.index).toBe(5);
      expect(breadcrumbs[29].data.index).toBe(34);
    });
  });

  describe('getBreadcrumbs', () => {
    it('should return empty array when no breadcrumbs', () => {
      expect(getBreadcrumbs()).toEqual([]);
    });

    it('should return a copy, not the original array', () => {
      addBreadcrumb('test', 'item', {});

      const crumbs1 = getBreadcrumbs();
      const crumbs2 = getBreadcrumbs();

      expect(crumbs1).not.toBe(crumbs2);
      expect(crumbs1).toEqual(crumbs2);
    });
  });

  describe('clearBreadcrumbs', () => {
    it('should remove all breadcrumbs', () => {
      addBreadcrumb('test', 'item1', {});
      addBreadcrumb('test', 'item2', {});

      clearBreadcrumbs();

      expect(getBreadcrumbs()).toEqual([]);
    });
  });

  describe('initBreadcrumbs', () => {
    describe('console wrapping', () => {
      it('should capture console.log calls', () => {
        initBreadcrumbs();

        console.log('test message');

        const breadcrumbs = getBreadcrumbs();
        const consoleBreadcrumb = breadcrumbs.find(b => b.type === 'console');
        expect(consoleBreadcrumb).toBeDefined();
        expect(consoleBreadcrumb.category).toBe('log');
        expect(consoleBreadcrumb.data.message).toContain('test message');
      });

      it('should capture console.warn calls', () => {
        initBreadcrumbs();

        console.warn('warning message');

        const breadcrumbs = getBreadcrumbs();
        const consoleBreadcrumb = breadcrumbs.find(b => b.category === 'warn');
        expect(consoleBreadcrumb).toBeDefined();
        expect(consoleBreadcrumb.data.message).toContain('warning message');
      });

      it('should capture console.error calls', () => {
        initBreadcrumbs();

        console.error('error message');

        const breadcrumbs = getBreadcrumbs();
        const consoleBreadcrumb = breadcrumbs.find(b => b.category === 'error');
        expect(consoleBreadcrumb).toBeDefined();
        expect(consoleBreadcrumb.data.message).toContain('error message');
      });

      it('should truncate long console messages', () => {
        initBreadcrumbs();

        const longMessage = 'x'.repeat(500);
        console.log(longMessage);

        const breadcrumbs = getBreadcrumbs();
        const consoleBreadcrumb = breadcrumbs.find(b => b.type === 'console');
        expect(consoleBreadcrumb.data.message.length).toBeLessThanOrEqual(200);
      });
    });

    describe('DOM event capturing', () => {
      it('should capture click events', () => {
        initBreadcrumbs();

        const button = document.createElement('button');
        button.id = 'test-button';
        button.className = 'btn primary';
        button.textContent = 'Click me';
        document.body.appendChild(button);

        button.click();

        const breadcrumbs = getBreadcrumbs();
        const clickBreadcrumb = breadcrumbs.find(b => b.category === 'click');

        expect(clickBreadcrumb).toBeDefined();
        expect(clickBreadcrumb.type).toBe('ui');
        expect(clickBreadcrumb.data.tag).toBe('BUTTON');
        expect(clickBreadcrumb.data.id).toBe('test-button');
        expect(clickBreadcrumb.data.className).toContain('btn');

        document.body.removeChild(button);
      });

      it('should truncate long class names', () => {
        initBreadcrumbs();

        const div = document.createElement('div');
        div.className = 'a'.repeat(200);
        document.body.appendChild(div);

        div.click();

        const breadcrumbs = getBreadcrumbs();
        const clickBreadcrumb = breadcrumbs.find(b => b.category === 'click');

        expect(clickBreadcrumb.data.className.length).toBeLessThanOrEqual(100);

        document.body.removeChild(div);
      });

      it('should truncate long text content', () => {
        initBreadcrumbs();

        const div = document.createElement('div');
        div.textContent = 'x'.repeat(100);
        document.body.appendChild(div);

        div.click();

        const breadcrumbs = getBreadcrumbs();
        const clickBreadcrumb = breadcrumbs.find(b => b.category === 'click');

        expect(clickBreadcrumb.data.text.length).toBeLessThanOrEqual(50);

        document.body.removeChild(div);
      });
    });

    describe('fetch wrapping', () => {
      let originalFetch;

      beforeEach(() => {
        // Reset wrappers so fetch can be wrapped fresh for each test
        _resetWrappers();
        clearBreadcrumbs();
        originalFetch = window.fetch;
        window.fetch = jest.fn().mockResolvedValue({ ok: true });
      });

      afterEach(() => {
        window.fetch = originalFetch;
      });

      it('should capture fetch requests', async () => {
        initBreadcrumbs();

        await window.fetch('/api/test', { method: 'POST' });

        const breadcrumbs = getBreadcrumbs();
        const fetchBreadcrumb = breadcrumbs.find(b => b.category === 'fetch');

        expect(fetchBreadcrumb).toBeDefined();
        expect(fetchBreadcrumb.type).toBe('http');
        expect(fetchBreadcrumb.data.method).toBe('POST');
        expect(fetchBreadcrumb.data.url).toBe('/api/test');
      });

      it('should default to GET method when not specified', async () => {
        initBreadcrumbs();

        await window.fetch('/api/test');

        const breadcrumbs = getBreadcrumbs();
        const fetchBreadcrumb = breadcrumbs.find(b => b.category === 'fetch');

        expect(fetchBreadcrumb.data.method).toBe('GET');
      });

      it('should truncate long URLs', async () => {
        initBreadcrumbs();

        const longUrl = '/api/' + 'x'.repeat(300);
        await window.fetch(longUrl);

        const breadcrumbs = getBreadcrumbs();
        const fetchBreadcrumb = breadcrumbs.find(b => b.category === 'fetch');

        expect(fetchBreadcrumb.data.url.length).toBeLessThanOrEqual(200);
      });
    });

    describe('XHR wrapping', () => {
      it('should capture XMLHttpRequest on send', () => {
        initBreadcrumbs();

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/xhr-test');
        xhr.send(); // Need to send to trigger the breadcrumb

        const breadcrumbs = getBreadcrumbs();
        const xhrBreadcrumb = breadcrumbs.find(b => b.category === 'xhr');

        expect(xhrBreadcrumb).toBeDefined();
        expect(xhrBreadcrumb.type).toBe('http');
        expect(xhrBreadcrumb.data.method).toBe('POST');
        expect(xhrBreadcrumb.data.url).toBe('/api/xhr-test');
      });
    });

    describe('router integration', () => {
      it('should capture route changes when router is provided', () => {
        const mockRouter = {
          afterEach: jest.fn(callback => {
            // Simulate a route change
            callback(
              { fullPath: '/new-page', name: 'NewPage' },
              { fullPath: '/old-page', name: 'OldPage' }
            );
          }),
        };

        initBreadcrumbs(mockRouter);

        const breadcrumbs = getBreadcrumbs();
        const routeBreadcrumb = breadcrumbs.find(b => b.category === 'route');

        expect(routeBreadcrumb).toBeDefined();
        expect(routeBreadcrumb.type).toBe('navigation');
        expect(routeBreadcrumb.data.from).toBe('/old-page');
        expect(routeBreadcrumb.data.to).toBe('/new-page');
        expect(routeBreadcrumb.data.name).toBe('NewPage');
      });

      it('should work without router', () => {
        // Should not throw
        expect(() => initBreadcrumbs()).not.toThrow();
      });
    });
  });
});

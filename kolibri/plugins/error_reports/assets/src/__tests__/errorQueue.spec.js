import {
  enqueue,
  getQueuedForTransmission,
  clearQueue,
  removeFromQueue,
  report,
  initErrorQueue,
  isStorageAvailable,
  _resetStorageCheck,
} from '../errorQueue';

// Mock dependencies
jest.mock('kolibri/client');
jest.mock('kolibri/urls', () => ({
  __esModule: true,
  default: {
    'kolibri:kolibri.plugins.error_reports:report': () => '/api/error-report/',
  },
}));

jest.mock('kolibri/internal/useConnection', () => {
  const ref = require('vue').ref;
  const connected = ref(true);
  return {
    __esModule: true,
    default: () => ({ connected }),
    _setConnected: val => {
      connected.value = val;
    },
  };
});

describe('errorQueue', () => {
  beforeEach(() => {
    // Clear queue before each test
    clearQueue();
    _resetStorageCheck();
    // Reset localStorage mock
    localStorage.clear();
    jest.clearAllMocks();
  });

  describe('isStorageAvailable', () => {
    it('should return true when localStorage is available', () => {
      expect(isStorageAvailable()).toBe(true);
    });

    it('should return false when localStorage throws', () => {
      // Reset cached value first
      _resetStorageCheck();

      // Use jest.spyOn to properly mock localStorage.setItem
      const setItemSpy = jest
        .spyOn(Storage.prototype, 'setItem')
        .mockImplementation(() => {
          throw new Error('Storage full');
        });

      expect(isStorageAvailable()).toBe(false);

      setItemSpy.mockRestore();
    });
  });

  describe('enqueue', () => {
    const createErrorData = (message = 'Test error', traceback = 'at test.js:1:1') => ({
      error_message: message,
      traceback,
      context: { browser: { name: 'Chrome' } },
    });

    it('should add a new error to the queue', () => {
      const errorData = createErrorData();
      const result = enqueue(errorData);

      expect(result.queued).toBe(true);
      expect(result.deduplicated).toBe(false);
      expect(result.count).toBe(1);
    });

    it('should deduplicate errors with the same fingerprint within the time window', () => {
      const errorData = createErrorData();

      const result1 = enqueue(errorData);
      expect(result1.count).toBe(1);
      expect(result1.deduplicated).toBe(false);

      const result2 = enqueue(errorData);
      expect(result2.count).toBe(2);
      expect(result2.deduplicated).toBe(true);

      const result3 = enqueue(errorData);
      expect(result3.count).toBe(3);
      expect(result3.deduplicated).toBe(true);
    });

    it('should treat errors with different messages as separate', () => {
      const error1 = createErrorData('Error 1');
      const error2 = createErrorData('Error 2');

      enqueue(error1);
      enqueue(error2);

      const queued = getQueuedForTransmission();
      expect(queued.length).toBe(2);
    });

    it('should treat errors with different stack traces as separate', () => {
      const error1 = createErrorData('Same error', 'at file1.js:1:1');
      const error2 = createErrorData('Same error', 'at file2.js:2:2');

      enqueue(error1);
      enqueue(error2);

      const queued = getQueuedForTransmission();
      expect(queued.length).toBe(2);
    });

    it('should ignore line/column numbers when fingerprinting', () => {
      const error1 = createErrorData('Test error', 'at test.js:1:1\nat other.js:10:5');
      const error2 = createErrorData('Test error', 'at test.js:99:99\nat other.js:200:100');

      enqueue(error1);
      const result = enqueue(error2);

      expect(result.deduplicated).toBe(true);
      expect(result.count).toBe(2);
    });

    it('should limit queue size to MAX_QUEUED_ERRORS', () => {
      // Add more than the max
      for (let i = 0; i < 60; i++) {
        enqueue(createErrorData(`Error ${i}`, `at file${i}.js:1:1`));
      }

      const queued = getQueuedForTransmission();
      expect(queued.length).toBe(50); // MAX_QUEUED_ERRORS
    });

    it('should remove oldest errors when queue is full', () => {
      for (let i = 0; i < 55; i++) {
        enqueue(createErrorData(`Error ${i}`, `at file${i}.js:1:1`));
      }

      const queued = getQueuedForTransmission();
      // First 5 errors should have been removed
      expect(queued.find(e => e.error_message === 'Error 0')).toBeUndefined();
      expect(queued.find(e => e.error_message === 'Error 54')).toBeDefined();
    });

    it('should use in-memory Map when storage is unavailable', () => {
      // Simulate storage unavailable using jest.spyOn - BEFORE reset/clear
      const setItemSpy = jest
        .spyOn(Storage.prototype, 'setItem')
        .mockImplementation(() => {
          throw new Error('Storage full');
        });

      // Reset and clear AFTER the spy is in place
      _resetStorageCheck();
      clearQueue();

      enqueue(createErrorData('Memory error'));

      const queued = getQueuedForTransmission();
      expect(queued.length).toBe(1);
      expect(queued[0].error_message).toBe('Memory error');

      setItemSpy.mockRestore();
    });
  });

  describe('getQueuedForTransmission', () => {
    const createErrorData = (message = 'Test error') => ({
      error_message: message,
      traceback: 'at test.js:1:1',
      context: { browser: { name: 'Chrome' } },
    });

    it('should return empty array when queue is empty', () => {
      const queued = getQueuedForTransmission();
      expect(queued).toEqual([]);
    });

    it('should strip internal fields from returned errors', () => {
      enqueue(createErrorData());
      const queued = getQueuedForTransmission();

      expect(queued[0]._fingerprint).toBeUndefined();
      expect(queued[0]._firstSeen).toBeUndefined();
      expect(queued[0]._lastSeen).toBeUndefined();
      expect(queued[0]._count).toBeUndefined();
    });

    it('should include deduplication info when count > 1', () => {
      const errorData = createErrorData();
      enqueue(errorData);
      enqueue(errorData);
      enqueue(errorData);

      const queued = getQueuedForTransmission();

      expect(queued[0].context.deduplication).toBeDefined();
      expect(queued[0].context.deduplication.count).toBe(3);
      expect(queued[0].context.deduplication.first_seen).toBeDefined();
      expect(queued[0].context.deduplication.last_seen).toBeDefined();
    });

    it('should not include deduplication info when count is 1', () => {
      enqueue(createErrorData());
      const queued = getQueuedForTransmission();

      expect(queued[0].context.deduplication).toBeUndefined();
    });
  });

  describe('clearQueue', () => {
    it('should remove all errors from the queue', () => {
      enqueue({ error_message: 'Error 1', traceback: 'stack1', context: {} });
      enqueue({ error_message: 'Error 2', traceback: 'stack2', context: {} });

      clearQueue();

      const queued = getQueuedForTransmission();
      expect(queued).toEqual([]);
    });

    it('should clear both localStorage and memory queue', () => {
      enqueue({ error_message: 'Error', traceback: 'stack', context: {} });

      clearQueue();

      expect(localStorage.getItem('kolibri_error_queue')).toBeNull();
      expect(getQueuedForTransmission()).toEqual([]);
    });
  });

  describe('removeFromQueue', () => {
    it('should remove specified number of errors from front of queue', () => {
      enqueue({ error_message: 'Error 1', traceback: 'stack1', context: {} });
      enqueue({ error_message: 'Error 2', traceback: 'stack2', context: {} });
      enqueue({ error_message: 'Error 3', traceback: 'stack3', context: {} });

      removeFromQueue(2);

      const queued = getQueuedForTransmission();
      expect(queued.length).toBe(1);
      expect(queued[0].error_message).toBe('Error 3');
    });
  });

  describe('report', () => {
    const client = require('kolibri/client').default;
    const useConnection = require('kolibri/internal/useConnection');

    beforeEach(() => {
      client.mockReset();
      client.mockResolvedValue({ data: { id: 1 } });
      useConnection._setConnected(true);
      // Ensure navigator.onLine is true
      Object.defineProperty(navigator, 'onLine', { value: true, writable: true });
    });

    it('should enqueue error and attempt to flush when online', async () => {
      const errorData = { error_message: 'Test', traceback: 'stack', context: {} };

      await report(errorData);

      expect(client).toHaveBeenCalled();
    });

    it('should return deduplicated true for duplicate errors via enqueue', () => {
      // Test deduplication via enqueue directly, not report
      // since report flushes the queue on first call
      const errorData = { error_message: 'Test', traceback: 'stack', context: {} };

      const result1 = enqueue(errorData);
      expect(result1.deduplicated).toBe(false);

      const result2 = enqueue(errorData);
      expect(result2.deduplicated).toBe(true);
      expect(result2.count).toBe(2);
    });

    it('should queue error when offline', async () => {
      Object.defineProperty(navigator, 'onLine', { value: false, writable: true });

      const errorData = { error_message: 'Offline error', traceback: 'stack', context: {} };
      await report(errorData);

      // Should not attempt to send
      expect(client).not.toHaveBeenCalled();

      // But should be in queue
      const queued = getQueuedForTransmission();
      expect(queued.length).toBe(1);
    });

    it('should queue error when disconnected', async () => {
      useConnection._setConnected(false);

      const errorData = { error_message: 'Disconnected error', traceback: 'stack', context: {} };
      await report(errorData);

      expect(client).not.toHaveBeenCalled();
      expect(getQueuedForTransmission().length).toBe(1);
    });
  });

  describe('initErrorQueue', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('should set up online event listener', () => {
      const addEventListenerSpy = jest.spyOn(window, 'addEventListener');

      initErrorQueue();

      expect(addEventListenerSpy).toHaveBeenCalledWith('online', expect.any(Function));
    });

    it('should set up periodic flush interval', () => {
      const setIntervalSpy = jest.spyOn(global, 'setInterval');

      initErrorQueue();

      expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 60000);
    });
  });

  describe('deduplication time window', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('should not deduplicate after time window expires', () => {
      const errorData = { error_message: 'Test', traceback: 'stack', context: {} };

      enqueue(errorData);

      // Advance time past the dedup window (60 seconds)
      jest.advanceTimersByTime(61000);

      const result = enqueue(errorData);

      // Should be treated as new error, not deduplicated
      expect(result.deduplicated).toBe(false);
    });
  });
});

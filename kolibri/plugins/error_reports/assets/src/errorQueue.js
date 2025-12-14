import Lockr from 'lockr';
import useConnection from 'kolibri/internal/useConnection';
import { get } from '@vueuse/core';
import client from 'kolibri/client';
import urls from 'kolibri/urls';

const QUEUE_KEY = 'kolibri_error_queue';
const MAX_QUEUED_ERRORS = 50;
const MAX_ERROR_AGE_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
const DEDUP_WINDOW_MS = 60000; // 1 minute

// In-memory fallback Map: fingerprint -> entry
// JS Maps preserve insertion order, so we get queue semantics
let memoryQueue = new Map();
let storageAvailable = null;

// For testing - reset storage availability check
export function _resetStorageCheck() {
  storageAvailable = null;
}

export function isStorageAvailable() {
  if (storageAvailable !== null) return storageAvailable;

  try {
    const testKey = '__kolibri_storage_test__';
    localStorage.setItem(testKey, 'test');
    localStorage.removeItem(testKey);
    storageAvailable = true;
  } catch {
    storageAvailable = false;
  }
  return storageAvailable;
}

function generateFingerprint(errorData) {
  const stackLines = (errorData.traceback || '')
    .split('\n')
    .slice(0, 4)
    .map(line => line.replace(/:\d+:\d+/g, ''))
    .join('|');
  return `${errorData.error_message}|${stackLines}`;
}

// Convert Map to array for storage
function mapToArray(map) {
  return Array.from(map.values());
}

// Convert array to Map, keyed by fingerprint
function arrayToMap(arr) {
  const map = new Map();
  for (const entry of arr) {
    map.set(entry._fingerprint, entry);
  }
  return map;
}

function getQueue() {
  if (!isStorageAvailable()) {
    return memoryQueue;
  }
  try {
    const arr = Lockr.get(QUEUE_KEY) || [];
    return arrayToMap(arr);
  } catch {
    return memoryQueue;
  }
}

function saveQueue(queue) {
  if (!isStorageAvailable()) {
    memoryQueue = queue;
    return;
  }
  try {
    Lockr.set(QUEUE_KEY, mapToArray(queue));
  } catch {
    // Storage full or failed - fall back to memory
    memoryQueue = queue;
  }
}

/**
 * Add error to queue, deduplicating if same error seen recently
 * Returns: { queued: boolean, deduplicated: boolean, count: number }
 */
export function enqueue(errorData) {
  const queue = getQueue();
  const now = Date.now();
  const fingerprint = generateFingerprint(errorData);

  // Clean expired entries
  for (const [key, entry] of queue) {
    if (now - entry._firstSeen > MAX_ERROR_AGE_MS) {
      queue.delete(key);
    }
  }

  // Check for duplicate within dedup window
  const existing = queue.get(fingerprint);

  if (existing && now - existing._lastSeen < DEDUP_WINDOW_MS) {
    existing._count++;
    existing._lastSeen = now;
    saveQueue(queue);
    return { queued: true, deduplicated: true, count: existing._count };
  }

  // New error (or outside dedup window) - add/replace in queue
  const entry = {
    ...errorData,
    _fingerprint: fingerprint,
    _firstSeen: now,
    _lastSeen: now,
    _count: existing ? existing._count + 1 : 1,
  };

  // Delete and re-add to move to end of Map (maintains insertion order)
  queue.delete(fingerprint);
  queue.set(fingerprint, entry);

  // Limit queue size - remove oldest (first) entries
  while (queue.size > MAX_QUEUED_ERRORS) {
    const firstKey = queue.keys().next().value;
    queue.delete(firstKey);
  }

  saveQueue(queue);
  return { queued: true, deduplicated: false, count: entry._count };
}

/**
 * Get all queued errors for transmission, cleaning internal fields
 */
export function getQueuedForTransmission() {
  const queue = getQueue();
  const results = [];

  for (const entry of queue.values()) {
    const { _fingerprint, _firstSeen, _lastSeen, _count, ...errorData } = entry;
    results.push({
      ...errorData,
      context: {
        ...errorData.context,
        ...(_count > 1 && {
          deduplication: {
            count: _count,
            first_seen: new Date(_firstSeen).toISOString(),
            last_seen: new Date(_lastSeen).toISOString(),
          },
        }),
      },
    });
  }

  return results;
}

export function clearQueue() {
  if (isStorageAvailable()) {
    try {
      Lockr.rm(QUEUE_KEY);
    } catch {
      // Ignore
    }
  }
  memoryQueue = new Map();
}

export function removeFromQueue(count) {
  const queue = getQueue();
  let removed = 0;

  for (const key of queue.keys()) {
    if (removed >= count) break;
    queue.delete(key);
    removed++;
  }

  saveQueue(queue);
}

async function flushQueue() {
  const { connected } = useConnection();

  if (!navigator.onLine || !get(connected)) {
    return;
  }

  const errors = getQueuedForTransmission();
  if (errors.length === 0) return;

  const url = urls['kolibri:kolibri.plugins.error_reports:report']();
  let successCount = 0;

  for (const errorData of errors) {
    try {
      await client({ url, method: 'post', data: errorData });
      successCount++;
    } catch (err) {
      if (!err.response) break; // Network error - stop
      successCount++; // Server error - count as handled
    }
  }

  if (successCount > 0) {
    removeFromQueue(successCount);
  }
}

export async function report(errorData) {
  const { queued, deduplicated, count } = enqueue(errorData);

  if (!deduplicated) {
    await flushQueue();
  }

  return { queued, deduplicated, count };
}

export function initErrorQueue() {
  flushQueue();
  window.addEventListener('online', flushQueue);
  setInterval(flushQueue, 60000);
}

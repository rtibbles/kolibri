import { ref } from 'vue';
import { get } from '@vueuse/core';

const MAX_RECENT_SEARCHES = 10;
const STORAGE_PREFIX = 'recentSearches_';

/**
 * Composable for managing recent search terms in localStorage.
 * Scoped per user ID.
 *
 * @param {Ref<string>} userId - Reactive ref to current user ID
 * @returns {{ recentSearches: Ref<string[]>, addSearch: (term: string) => void }}
 */
export default function useRecentSearches(userId) {
  const recentSearches = ref([]);

  function _storageKey() {
    return STORAGE_PREFIX + get(userId);
  }

  function _load() {
    try {
      const stored = localStorage.getItem(_storageKey());
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          recentSearches.value = parsed;
          return;
        }
      }
    } catch (e) {
      // Corrupted data - start fresh
    }
    recentSearches.value = [];
  }

  function _save() {
    try {
      localStorage.setItem(_storageKey(), JSON.stringify(recentSearches.value));
    } catch (e) {
      // localStorage full or unavailable - silently fail
    }
  }

  /**
   * Add a search term to recent searches.
   * Moves to front if already exists. Trims whitespace. Ignores empty strings.
   * @param {string} term
   */
  function addSearch(term) {
    const trimmed = (term || '').trim();
    if (!trimmed) return;

    // Remove existing duplicate
    const filtered = recentSearches.value.filter(t => t !== trimmed);
    // Add to front
    filtered.unshift(trimmed);
    // Limit to max
    recentSearches.value = filtered.slice(0, MAX_RECENT_SEARCHES);
    _save();
  }

  // Load on init
  _load();

  return {
    recentSearches,
    addSearch,
  };
}

import { ref } from 'vue';
import useRecentSearches from '../useRecentSearches';

// Mock localStorage
const mockStorage = {};
const localStorageMock = {
  getItem: jest.fn(key => mockStorage[key] || null),
  setItem: jest.fn((key, value) => {
    mockStorage[key] = value;
  }),
  removeItem: jest.fn(key => {
    delete mockStorage[key];
  }),
};

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('useRecentSearches', () => {
  beforeEach(() => {
    Object.keys(mockStorage).forEach(key => delete mockStorage[key]);
    jest.clearAllMocks();
  });

  describe('addSearch', () => {
    it('adds a search term to recent searches', () => {
      const userId = ref('user-1');
      const { addSearch, recentSearches } = useRecentSearches(userId);
      addSearch('fractions');
      expect(recentSearches.value).toContain('fractions');
    });

    it('persists to localStorage', () => {
      const userId = ref('user-1');
      const { addSearch } = useRecentSearches(userId);
      addSearch('fractions');
      expect(localStorageMock.setItem).toHaveBeenCalled();
    });

    it('does not add duplicate terms', () => {
      const userId = ref('user-1');
      const { addSearch, recentSearches } = useRecentSearches(userId);
      addSearch('fractions');
      addSearch('fractions');
      const count = recentSearches.value.filter(t => t === 'fractions').length;
      expect(count).toBe(1);
    });

    it('moves duplicate to front of list', () => {
      const userId = ref('user-1');
      const { addSearch, recentSearches } = useRecentSearches(userId);
      addSearch('fractions');
      addSearch('algebra');
      addSearch('fractions');
      expect(recentSearches.value[0]).toBe('fractions');
    });

    it('does not add empty strings', () => {
      const userId = ref('user-1');
      const { addSearch, recentSearches } = useRecentSearches(userId);
      addSearch('');
      expect(recentSearches.value.length).toBe(0);
    });

    it('trims whitespace', () => {
      const userId = ref('user-1');
      const { addSearch, recentSearches } = useRecentSearches(userId);
      addSearch('  fractions  ');
      expect(recentSearches.value[0]).toBe('fractions');
    });
  });

  describe('max items', () => {
    it('limits to 10 recent searches', () => {
      const userId = ref('user-1');
      const { addSearch, recentSearches } = useRecentSearches(userId);
      for (let i = 0; i < 15; i++) {
        addSearch(`search-${i}`);
      }
      expect(recentSearches.value.length).toBe(10);
    });

    it('removes oldest when limit exceeded', () => {
      const userId = ref('user-1');
      const { addSearch, recentSearches } = useRecentSearches(userId);
      for (let i = 0; i < 12; i++) {
        addSearch(`search-${i}`);
      }
      // Oldest (search-0, search-1) should be gone
      expect(recentSearches.value).not.toContain('search-0');
      expect(recentSearches.value).not.toContain('search-1');
      // Newest should be first
      expect(recentSearches.value[0]).toBe('search-11');
    });
  });

  describe('user scoping', () => {
    it('separates searches by user ID', () => {
      const userId1 = ref('user-1');
      const userId2 = ref('user-2');
      const search1 = useRecentSearches(userId1);
      const search2 = useRecentSearches(userId2);

      search1.addSearch('fractions');
      search2.addSearch('algebra');

      expect(search1.recentSearches.value).toContain('fractions');
      expect(search1.recentSearches.value).not.toContain('algebra');
    });
  });

  describe('loading from localStorage', () => {
    it('loads existing searches on init', () => {
      const userId = ref('user-1');
      mockStorage['recentSearches_user-1'] = JSON.stringify(['old-search']);
      const { recentSearches } = useRecentSearches(userId);
      expect(recentSearches.value).toContain('old-search');
    });

    it('handles corrupted localStorage gracefully', () => {
      const userId = ref('user-1');
      mockStorage['recentSearches_user-1'] = 'not-json{{{';
      const { recentSearches } = useRecentSearches(userId);
      expect(recentSearches.value).toEqual([]);
    });
  });
});

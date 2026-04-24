import { ref, nextTick } from 'vue';
import useFuzzyMetadataSearch, { getMatchedWordSegments } from '../useFuzzyMetadataSearch';

// Mock coreString to return readable translations from SCREAMING_SNAKE keys
const mockTranslations = {
  create: 'Create',
  explore: 'Explore',
  listen: 'Listen',
  practice: 'Practice',
  read: 'Read',
  school: 'School',
  mathematics: 'Mathematics',
  arts: 'Arts',
  dailyLife: 'Daily Life',
  preschool: 'Preschool',
  lowerPrimary: 'Lower Primary',
  upperPrimary: 'Upper Primary',
  signLanguage: 'Sign Language',
  captionsSubtitles: 'Captions/Subtitles',
  forBeginners: 'For Beginners',
  teacher: 'Teacher',
};

jest.mock('kolibri/uiText/commonCoreStrings', () => {
  const camelCase = require('lodash/camelCase');
  return {
    coreString: jest.fn(key => {
      return mockTranslations[camelCase(key)] || key;
    }),
  };
});

// Mock translated labels as they would come from useBaseSearch
const mockLabels = {
  learningActivitiesShown: {
    CREATE: 'UXADWcXZ',
    EXPLORE: '#j8L0eq3',
    LISTEN: 'mkA1R3NU',
    PRACTICE: 'VwRCom7G',
    READ: 'wA01urpi',
  },
  libraryCategories: {
    SCHOOL: {
      value: 'd&WXdXWF',
      nested: {
        MATHEMATICS: {
          value: 'd&WXdXWF.qs0Xlaxq',
          nested: {},
        },
        ARTS: {
          value: 'd&WXdXWF.5QAjgfv7',
          nested: {},
        },
      },
    },
    DAILY_LIFE: {
      value: '3qOg5Bau',
      nested: {},
    },
  },
  gradeLevelsList: ['PRESCHOOL', 'LOWER_PRIMARY', 'UPPER_PRIMARY'],
  accessibilityOptionsList: ['SIGN_LANGUAGE', 'CAPTIONS_SUBTITLES'],
  resourcesNeeded: {
    FOR_BEGINNERS: 'sccgQZDd.sAQsauuo',
    TEACHER: 'lsoCk5Uy.H&MVs7S#',
  },
  languagesList: [
    { id: 'en', lang_name: 'English' },
    { id: 'es', lang_name: 'Spanish' },
    { id: 'ar', lang_name: 'العربية' },
  ],
};

describe('useFuzzyMetadataSearch', () => {
  let searchableLabels;
  let fuzzySearch;

  beforeEach(() => {
    searchableLabels = ref(mockLabels);
    fuzzySearch = useFuzzyMetadataSearch(searchableLabels);
  });

  describe('search function', () => {
    it('returns empty array for empty query', () => {
      const results = fuzzySearch.search('');
      expect(results).toEqual([]);
    });

    it('returns empty array for single character query', () => {
      const results = fuzzySearch.search('c');
      expect(results).toEqual([]);
    });

    it('matches learning activities by label', () => {
      const results = fuzzySearch.search('create');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.filterKey === 'learning_activities');
      expect(match).toBeDefined();
      expect(match.filterValue).toBe('UXADWcXZ');
      expect(match.type).toBe('activity');
    });

    it('matches categories by name', () => {
      const results = fuzzySearch.search('math');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.filterKey === 'categories');
      expect(match).toBeDefined();
      expect(match.label).toBe('Mathematics');
    });

    it('matches grade levels', () => {
      const results = fuzzySearch.search('preschool');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.filterKey === 'grade_levels');
      expect(match).toBeDefined();
      expect(match.type).toBe('grade_level');
    });

    it('matches accessibility options', () => {
      const results = fuzzySearch.search('sign');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.filterKey === 'accessibility_labels');
      expect(match).toBeDefined();
    });

    it('matches languages by name', () => {
      const results = fuzzySearch.search('spanish');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.filterKey === 'languages');
      expect(match).toBeDefined();
      expect(match.filterValue).toBe('es');
    });

    it('matches resources needed', () => {
      const results = fuzzySearch.search('teacher');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.filterKey === 'learner_needs');
      expect(match).toBeDefined();
    });

    it('returns results with correct structure', () => {
      const results = fuzzySearch.search('create');
      expect(results.length).toBeGreaterThan(0);
      const result = results[0];
      expect(result).toHaveProperty('label');
      expect(result).toHaveProperty('filterKey');
      expect(result).toHaveProperty('filterValue');
      expect(result).toHaveProperty('type');
    });

    it('limits results to 3', () => {
      // With many possible matches, results should be bounded to 3
      const results = fuzzySearch.search('re');
      expect(results.length).toBeLessThanOrEqual(3);
    });
  });

  describe('fuzzy matching', () => {
    it('matches with typos/partial input', () => {
      const results = fuzzySearch.search('explor');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.label === 'Explore');
      expect(match).toBeDefined();
    });

    it('matches case-insensitively', () => {
      const results = fuzzySearch.search('CREATE');
      expect(results.length).toBeGreaterThan(0);
    });
  });

  describe('non-Latin script matching', () => {
    it('matches Arabic language names', () => {
      const results = fuzzySearch.search('العربية');
      expect(results.length).toBeGreaterThan(0);
      const match = results.find(r => r.filterValue === 'ar');
      expect(match).toBeDefined();
    });
  });

  describe('activity synonym matching', () => {
    it('matches WATCH when typing "video"', () => {
      // Add WATCH to mock labels
      searchableLabels.value = {
        ...mockLabels,
        learningActivitiesShown: {
          ...mockLabels.learningActivitiesShown,
          WATCH: 'zK2uu4kP',
        },
      };
      fuzzySearch = useFuzzyMetadataSearch(searchableLabels);
      const results = fuzzySearch.search('video');
      const match = results.find(r => r.filterKey === 'learning_activities' && r.key === 'WATCH');
      expect(match).toBeDefined();
    });

    it('matches LISTEN when typing "audio"', () => {
      const results = fuzzySearch.search('audio');
      const match = results.find(r => r.filterKey === 'learning_activities' && r.key === 'LISTEN');
      expect(match).toBeDefined();
    });

    it('matches READ when typing "book"', () => {
      const results = fuzzySearch.search('book');
      const match = results.find(r => r.filterKey === 'learning_activities' && r.key === 'READ');
      expect(match).toBeDefined();
    });

    it('matches PRACTICE when typing "quiz"', () => {
      const results = fuzzySearch.search('quiz');
      const match = results.find(
        r => r.filterKey === 'learning_activities' && r.key === 'PRACTICE',
      );
      expect(match).toBeDefined();
    });

    it('matches CREATE when typing "draw"', () => {
      const results = fuzzySearch.search('draw');
      const match = results.find(r => r.filterKey === 'learning_activities' && r.key === 'CREATE');
      expect(match).toBeDefined();
    });

    it('matches EXPLORE when typing "interactive"', () => {
      const results = fuzzySearch.search('interactive');
      const match = results.find(r => r.filterKey === 'learning_activities' && r.key === 'EXPLORE');
      expect(match).toBeDefined();
    });

    it('still shows the translated label, not the synonym', () => {
      const results = fuzzySearch.search('audio');
      const match = results.find(r => r.filterKey === 'learning_activities' && r.key === 'LISTEN');
      expect(match).toBeDefined();
      expect(match.label).toBe('Listen');
    });
  });

  describe('scoping', () => {
    it('updates results when searchableLabels changes', async () => {
      // Initially should find Mathematics
      let results = fuzzySearch.search('math');
      expect(results.find(r => r.label === 'Mathematics')).toBeDefined();

      // Update labels to remove categories
      searchableLabels.value = {
        ...mockLabels,
        libraryCategories: {},
      };

      // Wait for Vue's watch to fire
      await nextTick();

      // After update, Mathematics should not be found
      results = fuzzySearch.search('math');
      expect(results.find(r => r.label === 'Mathematics')).toBeUndefined();
    });
  });

  describe('removeMatchedWords', () => {
    it('removes category-matched word from keywords', () => {
      const filter = { label: 'Mathematics', type: 'category', filterKey: 'categories' };
      expect(fuzzySearch.removeMatchedWords('math videos', filter)).toBe('videos');
    });

    it('removes synonym-matched word for activity filters', () => {
      // Add WATCH to labels so the filter entity has .key
      searchableLabels.value = {
        ...mockLabels,
        learningActivitiesShown: {
          ...mockLabels.learningActivitiesShown,
          WATCH: 'zK2uu4kP',
        },
      };
      fuzzySearch = useFuzzyMetadataSearch(searchableLabels);
      const filter = {
        label: 'Watch',
        type: 'activity',
        key: 'WATCH',
        filterKey: 'learning_activities',
      };
      expect(fuzzySearch.removeMatchedWords('video', filter)).toBe('');
    });

    it('removes only matched words, keeps others', () => {
      const filter = { label: 'Mathematics', type: 'category', filterKey: 'categories' };
      expect(fuzzySearch.removeMatchedWords('fun math games', filter)).toBe('fun games');
    });

    it('returns original string when no words match', () => {
      const filter = { label: 'Mathematics', type: 'category', filterKey: 'categories' };
      expect(fuzzySearch.removeMatchedWords('fun games', filter)).toBe('fun games');
    });

    it('returns empty string for empty keywords', () => {
      const filter = { label: 'Mathematics', type: 'category', filterKey: 'categories' };
      expect(fuzzySearch.removeMatchedWords('', filter)).toBe('');
    });

    it('returns keywords unchanged when filter is null', () => {
      expect(fuzzySearch.removeMatchedWords('math videos', null)).toBe('math videos');
    });
  });
});

describe('getMatchedWordSegments', () => {
  it('marks matched words and preserves whitespace', () => {
    const filter = { label: 'Mathematics', type: 'category', filterKey: 'categories' };
    const segments = getMatchedWordSegments('math videos', filter);
    expect(segments).toEqual([
      { text: 'math', matched: true },
      { text: ' ', matched: false },
      { text: 'videos', matched: false },
    ]);
  });

  it('marks synonym matches for activities', () => {
    const filter = {
      label: 'Watch',
      type: 'activity',
      key: 'WATCH',
      filterKey: 'learning_activities',
    };
    const segments = getMatchedWordSegments('fun video stuff', filter);
    expect(segments).toEqual([
      { text: 'fun', matched: false },
      { text: ' ', matched: false },
      { text: 'video', matched: true },
      { text: ' ', matched: false },
      { text: 'stuff', matched: false },
    ]);
  });

  it('returns single unmatched segment for null filter', () => {
    const segments = getMatchedWordSegments('math videos', null);
    expect(segments).toEqual([{ text: 'math videos', matched: false }]);
  });

  it('returns single unmatched segment for empty keywords', () => {
    const filter = { label: 'Mathematics', type: 'category', filterKey: 'categories' };
    const segments = getMatchedWordSegments('', filter);
    expect(segments).toEqual([{ text: '', matched: false }]);
  });
});

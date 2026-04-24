import { shallowMount } from '@vue/test-utils';
import SearchAutocompleteDropdown from '../SearchAutocompleteDropdown.vue';

// Use encoded activity values matching the API format (from LearningActivities constants)
const WATCH_VALUE = 'UD5UGM0z';
const READ_VALUE = 'wA01urpi';

const mockHistoryItems = [
  {
    id: 'node-1',
    title: 'The Square Root Concept',
    learning_activities: [WATCH_VALUE],
    channel_title: 'Khan Academy',
  },
  {
    id: 'node-2',
    title: 'Understanding Fractions',
    learning_activities: [READ_VALUE],
    channel_title: 'CK-12',
  },
];

const mockRecentSearches = ['fraction videos', 'fraction video for kids'];

const mockSuggestions = [
  {
    id: 'node-3',
    title: 'Fraction Basics',
    type: 'content',
    learning_activities: [WATCH_VALUE],
  },
  {
    key: 'PRACTICE',
    label: 'Practice',
    filterKey: 'learning_activities',
    filterValue: 'PRACTICE',
    type: 'activity',
  },
];

function makeWrapper(propsData = {}) {
  return shallowMount(SearchAutocompleteDropdown, {
    propsData: {
      show: true,
      query: '',
      suggestions: [],
      historyItems: [],
      recentSearches: [],
      ...propsData,
    },
  });
}

describe('SearchAutocompleteDropdown', () => {
  describe('visibility', () => {
    it('is hidden when show is false', () => {
      const wrapper = makeWrapper({ show: false });
      expect(wrapper.find('[data-testid="autocomplete-dropdown"]').exists()).toBe(false);
    });

    it('is visible when show is true', () => {
      const wrapper = makeWrapper({ show: true });
      expect(wrapper.find('[data-testid="autocomplete-dropdown"]').exists()).toBe(true);
    });
  });

  describe('focus state (no query)', () => {
    it('renders history section header when history items exist', () => {
      const wrapper = makeWrapper({ historyItems: mockHistoryItems });
      expect(wrapper.find('[data-testid="history-section"]').exists()).toBe(true);
    });

    it('renders history items', () => {
      const wrapper = makeWrapper({ historyItems: mockHistoryItems });
      const items = wrapper.findAll('[data-testid="history-item"]');
      expect(items.length).toBe(2);
    });

    it('renders recent searches section when recent searches exist', () => {
      const wrapper = makeWrapper({ recentSearches: mockRecentSearches });
      expect(wrapper.find('[data-testid="recent-searches-section"]').exists()).toBe(true);
    });

    it('renders recent search items', () => {
      const wrapper = makeWrapper({ recentSearches: mockRecentSearches });
      const items = wrapper.findAll('[data-testid="recent-search-item"]');
      expect(items.length).toBe(2);
    });

    it('emits selectContent when a history item is clicked', async () => {
      const wrapper = makeWrapper({ historyItems: mockHistoryItems });
      const item = wrapper.findAll('[data-testid="history-item"]').at(0);
      await item.trigger('click');
      expect(wrapper.emitted('selectContent')).toBeTruthy();
      expect(wrapper.emitted('selectContent')[0][0]).toEqual(mockHistoryItems[0]);
    });

    it('emits selectSearch when a recent search is clicked', async () => {
      const wrapper = makeWrapper({ recentSearches: mockRecentSearches });
      const item = wrapper.findAll('[data-testid="recent-search-item"]').at(0);
      await item.trigger('click');
      expect(wrapper.emitted('selectSearch')).toBeTruthy();
      expect(wrapper.emitted('selectSearch')[0][0]).toBe('fraction videos');
    });

    it('renders nothing when no history or recent searches', () => {
      const wrapper = makeWrapper();
      expect(wrapper.findAll('[data-testid="history-item"]').length).toBe(0);
      expect(wrapper.findAll('[data-testid="recent-search-item"]').length).toBe(0);
    });
  });

  describe('typing state (has query)', () => {
    it('renders suggestion items', () => {
      const wrapper = makeWrapper({
        query: 'frac',
        suggestions: mockSuggestions,
      });
      const contentItems = wrapper.findAll('[data-testid="suggestion-item"]');
      const filterPills = wrapper.findAll('[data-testid="filter-suggestion-pill"]');
      expect(contentItems.length + filterPills.length).toBe(2);
    });

    it('does not render history or recent searches when query is present', () => {
      const wrapper = makeWrapper({
        query: 'frac',
        suggestions: mockSuggestions,
        historyItems: mockHistoryItems,
        recentSearches: mockRecentSearches,
      });
      expect(wrapper.find('[data-testid="history-section"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="recent-searches-section"]').exists()).toBe(false);
    });

    it('emits selectContent when a content suggestion is clicked', async () => {
      const wrapper = makeWrapper({
        query: 'frac',
        suggestions: mockSuggestions,
      });
      const items = wrapper.findAll('[data-testid="suggestion-item"]');
      await items.at(0).trigger('click');
      expect(wrapper.emitted('selectContent')).toBeTruthy();
      expect(wrapper.emitted('selectContent')[0][0]).toMatchObject({ id: 'node-3' });
    });

    it('emits selectFilter when a metadata suggestion is clicked', async () => {
      const wrapper = makeWrapper({
        query: 'frac',
        suggestions: mockSuggestions,
      });
      const pills = wrapper.findAll('[data-testid="filter-suggestion-pill"]');
      await pills.at(0).trigger('click');
      expect(wrapper.emitted('selectFilter')).toBeTruthy();
      expect(wrapper.emitted('selectFilter')[0][0]).toMatchObject({
        filterKey: 'learning_activities',
        filterValue: 'PRACTICE',
      });
    });

    it('renders empty state when no suggestions', () => {
      const wrapper = makeWrapper({
        query: 'xyznoexist',
        suggestions: [],
      });
      expect(wrapper.findAll('[data-testid="suggestion-item"]').length).toBe(0);
    });
  });

  describe('accessibility', () => {
    it('has role="menu" on the dropdown', () => {
      const wrapper = makeWrapper({
        historyItems: mockHistoryItems,
      });
      expect(wrapper.find('[data-testid="autocomplete-dropdown"]').attributes('role')).toBe('menu');
    });

    it('items have role="menuitem"', () => {
      const wrapper = makeWrapper({
        historyItems: mockHistoryItems,
      });
      const items = wrapper.findAll('[data-testid="history-item"]');
      expect(items.at(0).attributes('role')).toBe('menuitem');
    });
  });
});

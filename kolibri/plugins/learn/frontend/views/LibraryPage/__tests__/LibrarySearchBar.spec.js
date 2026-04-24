import { ref } from 'vue';
import { shallowMount } from '@vue/test-utils';
import LibrarySearchBar from '../LibrarySearchBar.vue';

const mockAddSearch = jest.fn();
const mockAutoCompleteHandler = jest.fn();

// Mock composables used in setup()
jest.mock('kolibri/composables/useUser', () => ({
  __esModule: true,
  default: jest.fn(() => ({
    user_id: require('vue').ref('test-user'),
  })),
}));

jest.mock('kolibri-common/composables/useRecentSearches', () => ({
  __esModule: true,
  default: jest.fn(() => ({
    recentSearches: require('vue').ref(['fraction videos']),
    addSearch: mockAddSearch,
  })),
}));

jest.mock('../../../composables/useLearnerResources', () => ({
  __esModule: true,
  default: jest.fn(() => ({
    resumableContentNodes: require('vue').computed(() => [
      { id: 'node-1', title: 'Recent Video', learning_activities: ['WATCH'] },
    ]),
  })),
}));

function makeWrapper(propsData = {}, provides = {}) {
  return shallowMount(LibrarySearchBar, {
    propsData: {
      value: '',
      ...propsData,
    },
    provide: {
      keyWordAutoCompleteHandler: mockAutoCompleteHandler,
      autoCompleteSuggestions: ref([]),
      messages: ref([]),
      ...provides,
    },
    stubs: ['SearchAutocompleteDropdown'],
  });
}

describe('LibrarySearchBar', () => {
  beforeEach(() => {
    mockAutoCompleteHandler.mockClear();
    mockAddSearch.mockClear();
  });

  describe('rendering', () => {
    it('renders a search input', () => {
      const wrapper = makeWrapper();
      expect(wrapper.find('input[type="search"]').exists()).toBe(true);
    });

    it('renders an "All filters" button', () => {
      const wrapper = makeWrapper();
      const filterBtn = wrapper.find('[data-testid="all-filters-button"]');
      expect(filterBtn.exists()).toBe(true);
    });

    it('renders a search submit button', () => {
      const wrapper = makeWrapper();
      const searchBtn = wrapper.find('[data-testid="search-submit-button"]');
      expect(searchBtn.exists()).toBe(true);
    });

    it('renders SearchAutocompleteDropdown component', () => {
      const wrapper = makeWrapper();
      expect(wrapper.find('searchautocompletedropdown-stub').exists()).toBe(true);
    });
  });

  describe('clear button', () => {
    it('shows clear button when input has text', () => {
      const wrapper = makeWrapper({ value: 'fraction' });
      const clearBtn = wrapper.find('[data-testid="search-clear-button"]');
      expect(clearBtn.exists()).toBe(true);
    });

    it('emits clear event when clear button is clicked', async () => {
      const wrapper = makeWrapper({ value: 'fraction' });
      const clearBtn = wrapper.find('[data-testid="search-clear-button"]');
      clearBtn.vm.$emit('click');
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted('clear')).toBeTruthy();
    });

    it('calls autocomplete handler with empty string on clear', async () => {
      const wrapper = makeWrapper({ value: 'fraction' });
      const clearBtn = wrapper.find('[data-testid="search-clear-button"]');
      clearBtn.vm.$emit('click');
      await wrapper.vm.$nextTick();
      expect(mockAutoCompleteHandler).toHaveBeenCalledWith('');
    });
  });

  describe('events', () => {
    it('emits input event on text change', async () => {
      const wrapper = makeWrapper();
      const input = wrapper.find('input[type="search"]');
      await input.setValue('frac');
      expect(wrapper.emitted('input')).toBeTruthy();
      expect(wrapper.emitted('input')[0]).toEqual(['frac']);
    });

    it('calls autocomplete handler on text change', async () => {
      const wrapper = makeWrapper();
      const input = wrapper.find('input[type="search"]');
      await input.setValue('frac');
      expect(mockAutoCompleteHandler).toHaveBeenCalledWith('frac');
    });

    it('emits search event on form submit', async () => {
      const wrapper = makeWrapper({ value: 'fraction' });
      await wrapper.find('form').trigger('submit');
      expect(wrapper.emitted('search')).toBeTruthy();
      expect(wrapper.emitted('search')[0]).toEqual(['fraction']);
    });

    it('emits search event on enter key', async () => {
      const wrapper = makeWrapper({ value: 'fraction' });
      await wrapper.find('input[type="search"]').trigger('keydown.enter');
      expect(wrapper.emitted('search')).toBeTruthy();
    });

    it('emits openFilters event when "All filters" button is clicked', async () => {
      const wrapper = makeWrapper();
      const filterBtn = wrapper.find('[data-testid="all-filters-button"]');
      filterBtn.vm.$emit('click');
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted('openFilters')).toBeTruthy();
    });
  });

  describe('autocomplete dropdown', () => {
    it('passes query prop to dropdown', () => {
      const wrapper = makeWrapper({ value: 'fraction' });
      const dropdown = wrapper.find('searchautocompletedropdown-stub');
      expect(dropdown.attributes('query')).toBe('fraction');
    });

    it('emits selectContent when dropdown emits selectContent', async () => {
      const wrapper = makeWrapper();
      const dropdown = wrapper.find('searchautocompletedropdown-stub');
      const item = { id: 'node-1', title: 'Test' };
      dropdown.vm.$emit('selectContent', item);
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted('selectContent')).toBeTruthy();
      expect(wrapper.emitted('selectContent')[0][0]).toEqual(item);
    });

    it('emits selectFilter when dropdown emits selectFilter', async () => {
      const wrapper = makeWrapper();
      const dropdown = wrapper.find('searchautocompletedropdown-stub');
      const filter = { filterKey: 'categories', filterValue: 'math_id' };
      dropdown.vm.$emit('selectFilter', filter);
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted('selectFilter')).toBeTruthy();
      expect(wrapper.emitted('selectFilter')[0][0]).toEqual(filter);
    });

    it('emits search on selectSearch from dropdown', async () => {
      const wrapper = makeWrapper();
      const dropdown = wrapper.find('searchautocompletedropdown-stub');
      dropdown.vm.$emit('selectSearch', 'fraction');
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted('search')).toBeTruthy();
      expect(wrapper.emitted('search')[0]).toEqual(['fraction']);
    });
  });

  describe('props', () => {
    it('displays the value prop in the input', () => {
      const wrapper = makeWrapper({ value: 'test search' });
      expect(wrapper.find('input[type="search"]').element.value).toBe('test search');
    });
  });
});

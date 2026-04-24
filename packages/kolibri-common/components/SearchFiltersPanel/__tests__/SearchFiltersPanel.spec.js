import { ref } from 'vue';
import { shallowMount } from '@vue/test-utils';
import SearchFiltersPanel from '../index.vue';

const defaultSearchTerms = {
  learning_activities: {},
  learner_needs: {},
  accessibility_labels: {},
  languages: {},
  grade_levels: {},
  categories: {},
  keywords: '',
};

function makeWrapper(propsData = {}) {
  return shallowMount(SearchFiltersPanel, {
    propsData: {
      value: { ...defaultSearchTerms },
      ...propsData,
    },
    provide: {
      availableLibraryCategories: ref({}),
      availableResourcesNeeded: ref({}),
      searchableLabels: ref(null),
      activeSearchTerms: ref({}),
      searchLoading: ref(false),
    },
  });
}

describe('SearchFiltersPanel', () => {
  describe('hideKeywords prop', () => {
    it('shows keywords section by default', () => {
      const wrapper = makeWrapper();
      const searchBox = wrapper.findComponent({ name: 'SearchBox' });
      expect(searchBox.exists()).toBe(true);
    });

    it('hides keywords section when hideKeywords is true', () => {
      const wrapper = makeWrapper({ hideKeywords: true });
      const searchBox = wrapper.findComponent({ name: 'SearchBox' });
      expect(searchBox.exists()).toBe(false);
    });

    it('hides keywords heading when hideKeywords is true', () => {
      const wrapper = makeWrapper({ hideKeywords: true });
      expect(wrapper.text()).not.toContain('Keywords');
    });
  });
});

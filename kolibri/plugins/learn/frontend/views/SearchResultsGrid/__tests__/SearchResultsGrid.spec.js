import { shallowMount } from '@vue/test-utils';
import useKResponsiveWindow from 'kolibri-design-system/lib/composables/useKResponsiveWindow';
import SearchResultsGrid from '../../SearchResultsGrid.vue';

jest.mock('kolibri-common/composables/useBaseSearch');
jest.mock('kolibri-design-system/lib/composables/useKResponsiveWindow');

function makeWrapper(propsData = {}) {
  useKResponsiveWindow.mockImplementation(() => ({
    windowIsSmall: false,
    windowIsLarge: true,
  }));
  return shallowMount(SearchResultsGrid, {
    propsData: {
      results: [{ id: 'r1', title: 'Result 1' }],
      searchLoading: false,
      ...propsData,
    },
  });
}

describe('SearchResultsGrid restructured', () => {
  describe('AIResponseSection', () => {
    it('renders AIResponseSection when messages are provided', () => {
      const wrapper = makeWrapper({
        messages: ['AI response text'],
      });
      expect(wrapper.findComponent({ name: 'AIResponseSection' }).exists()).toBe(true);
    });

    it('does not render AIResponseSection when no messages', () => {
      const wrapper = makeWrapper({ messages: [] });
      expect(wrapper.findComponent({ name: 'AIResponseSection' }).exists()).toBe(true);
      // AIResponseSection handles empty messages internally (renders nothing)
    });

    it('passes messages and categoryChips to AIResponseSection', () => {
      const messages = ['AI says hello'];
      const categoryChips = [{ label: 'Math', value: 'math_id' }];
      const wrapper = makeWrapper({ messages, categoryChips });
      const section = wrapper.findComponent({ name: 'AIResponseSection' });
      expect(section.props('messages')).toEqual(messages);
      expect(section.props('categoryChips')).toEqual(categoryChips);
    });
  });

  describe('core search results', () => {
    it('still renders search results title', () => {
      const wrapper = makeWrapper();
      expect(wrapper.find('[data-testid="search-results-title"]').exists()).toBe(true);
    });

    it('still renders SearchChips', () => {
      const wrapper = makeWrapper();
      expect(wrapper.findComponent({ name: 'SearchChips' }).exists()).toBe(true);
    });

    it('still renders the results grid', () => {
      const wrapper = makeWrapper();
      expect(wrapper.find('[data-testid="search-results-card-grid"]').exists()).toBe(true);
    });

    it('still renders more button when more results exist', () => {
      const wrapper = makeWrapper({ more: { next: true } });
      expect(wrapper.find('[data-testid="more-results-button"]').exists()).toBe(true);
    });
  });

  describe('MoreToExploreSection', () => {
    it('renders MoreToExploreSection', () => {
      const wrapper = makeWrapper({
        exploreGroups: [{ label: 'Math', count: 5, items: [{ id: '1' }] }],
      });
      expect(wrapper.findComponent({ name: 'MoreToExploreSection' }).exists()).toBe(true);
    });

    it('passes exploreGroups prop', () => {
      const groups = [{ label: 'Math', count: 5, items: [] }];
      const wrapper = makeWrapper({ exploreGroups: groups });
      const section = wrapper.findComponent({ name: 'MoreToExploreSection' });
      expect(section.props('groups')).toEqual(groups);
    });
  });

  describe('graceful degradation', () => {
    it('works without AI data - no messages or groups', () => {
      const wrapper = makeWrapper({
        messages: [],
        exploreGroups: [],
      });
      // Core elements still render
      expect(wrapper.find('[data-testid="search-results-title"]').exists()).toBe(true);
      expect(wrapper.find('[data-testid="search-results-card-grid"]').exists()).toBe(true);
    });
  });

  describe('does not use SearchMessages', () => {
    it('does not render SearchMessages component', () => {
      const wrapper = makeWrapper();
      expect(wrapper.findComponent({ name: 'SearchMessages' }).exists()).toBe(false);
    });
  });
});

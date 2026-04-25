import { ref } from 'vue';
import { shallowMount } from '@vue/test-utils';
import HorizontalFilterPills from '../HorizontalFilterPills.vue';

const mockActivities = {
  CREATE: 'UXADWcXZ',
  EXPLORE: '#j8L0eq3',
  LISTEN: 'mkA1R3NU',
};

const mockCategories = {
  SCHOOL: {
    value: 'd&WXdXWF',
    nested: {},
  },
  DAILY_LIFE: {
    value: '3qOg5Bau',
    nested: {},
  },
};

function makeWrapper(provides = {}) {
  const toggleFilter = jest.fn();
  return {
    toggleFilter,
    wrapper: shallowMount(HorizontalFilterPills, {
      provide: {
        availableLearningActivities: ref(mockActivities),
        availableLibraryCategories: ref(mockCategories),
        searchableLabels: ref(null),
        isFilterActive: () => false,
        isLabelAvailable: () => true,
        appliedFilters: () => [],
        toggleFilter,
        searchLoading: ref(false),
        ...provides,
      },
    }),
  };
}

describe('HorizontalFilterPills', () => {
  describe('activity pills', () => {
    it('renders activity pill buttons', () => {
      const { wrapper } = makeWrapper();
      const activityPills = wrapper.findAll('[data-testid="activity-pill"]');
      expect(activityPills.length).toBe(3);
    });

    it('calls toggleFilter when an activity pill is clicked', async () => {
      const { wrapper, toggleFilter } = makeWrapper();
      const activityPills = wrapper.findAll('[data-testid="activity-pill"]');
      activityPills.at(0).vm.$emit('click');
      await wrapper.vm.$nextTick();
      expect(toggleFilter).toHaveBeenCalledWith(
        expect.objectContaining({ key: 'learning_activities' }),
      );
    });
  });

  describe('category pills', () => {
    it('renders category pill buttons', () => {
      const { wrapper } = makeWrapper();
      const categoryPills = wrapper.findAll('[data-testid="category-pill"]');
      expect(categoryPills.length).toBe(2);
    });

    it('calls toggleFilter when a category pill is clicked', async () => {
      const { wrapper, toggleFilter } = makeWrapper();
      const categoryPills = wrapper.findAll('[data-testid="category-pill"]');
      categoryPills.at(0).vm.$emit('click');
      await wrapper.vm.$nextTick();
      expect(toggleFilter).toHaveBeenCalledWith(expect.objectContaining({ key: 'categories' }));
    });
  });

  describe('when no data', () => {
    it('renders no activity pills when activities empty', () => {
      const { wrapper } = makeWrapper({
        availableLearningActivities: ref({}),
      });
      expect(wrapper.findAll('[data-testid="activity-pill"]').length).toBe(0);
    });

    it('renders no category pills when categories empty', () => {
      const { wrapper } = makeWrapper({
        availableLibraryCategories: ref({}),
      });
      expect(wrapper.findAll('[data-testid="category-pill"]').length).toBe(0);
    });
  });

  describe('availability filtering', () => {
    it('hides catalog labels not in searchableLabels', () => {
      const { wrapper } = makeWrapper({
        isLabelAvailable: (key, value) =>
          key === 'learning_activities' ? value === '#j8L0eq3' : false,
      });
      expect(wrapper.findAll('[data-testid="activity-pill"]').length).toBe(1);
      expect(wrapper.findAll('[data-testid="category-pill"]').length).toBe(0);
    });

    it('keeps an active catalog label visible even when not in searchableLabels', () => {
      const { wrapper } = makeWrapper({
        isLabelAvailable: () => false,
        appliedFilters: () => [{ key: 'learning_activities', value: 'UXADWcXZ' }],
        isFilterActive: (key, value) => key === 'learning_activities' && value === 'UXADWcXZ',
      });
      expect(wrapper.findAll('[data-testid="activity-pill"]').length).toBe(1);
    });
  });

  describe('applied filters', () => {
    it('renders the keyword as a leading pill', () => {
      const { wrapper } = makeWrapper({
        appliedFilters: () => [{ key: 'keywords', value: 'hummingbirds' }],
        isFilterActive: (key, value) => key === 'keywords' && value === 'hummingbirds',
      });
      const keywordPill = wrapper.find('[data-testid="keyword-pill"]');
      expect(keywordPill.exists()).toBe(true);
      expect(keywordPill.attributes('text')).toBe('hummingbirds');
    });

    it('renders an active filter from a non-catalog dimension', () => {
      const { wrapper } = makeWrapper({
        appliedFilters: () => [{ key: 'grade_levels', value: 'basic_skills' }],
        isFilterActive: (key, value) => key === 'grade_levels' && value === 'basic_skills',
      });
      expect(wrapper.find('[data-testid="grade_levels-pill"]').exists()).toBe(true);
    });
  });
});

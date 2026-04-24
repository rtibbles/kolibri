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
  return shallowMount(HorizontalFilterPills, {
    provide: {
      availableLearningActivities: ref(mockActivities),
      availableLibraryCategories: ref(mockCategories),
      activeSearchTerms: ref({ learning_activities: {}, categories: {} }),
      searchLoading: ref(false),
      ...provides,
    },
  });
}

describe('HorizontalFilterPills', () => {
  describe('activity pills', () => {
    it('renders activity pill buttons', () => {
      const wrapper = makeWrapper();
      const activityPills = wrapper.findAll('[data-test="activity-pill"]');
      expect(activityPills.length).toBe(3);
    });

    it('emits toggleFilter when an activity pill is clicked', async () => {
      const wrapper = makeWrapper();
      const activityPills = wrapper.findAll('[data-test="activity-pill"]');
      activityPills.at(0).vm.$emit('click');
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted('toggleFilter')).toBeTruthy();
      expect(wrapper.emitted('toggleFilter')[0][0]).toMatchObject({
        key: 'learning_activities',
      });
    });
  });

  describe('category pills', () => {
    it('renders category pill buttons', () => {
      const wrapper = makeWrapper();
      const categoryPills = wrapper.findAll('[data-test="category-pill"]');
      expect(categoryPills.length).toBe(2);
    });

    it('emits toggleFilter when a category pill is clicked', async () => {
      const wrapper = makeWrapper();
      const categoryPills = wrapper.findAll('[data-test="category-pill"]');
      categoryPills.at(0).vm.$emit('click');
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted('toggleFilter')).toBeTruthy();
      expect(wrapper.emitted('toggleFilter')[0][0]).toMatchObject({
        key: 'categories',
      });
    });
  });

  describe('when no data', () => {
    it('renders no activity pills when activities empty', () => {
      const wrapper = makeWrapper({
        availableLearningActivities: ref({}),
      });
      expect(wrapper.findAll('[data-test="activity-pill"]').length).toBe(0);
    });

    it('renders no category pills when categories empty', () => {
      const wrapper = makeWrapper({
        availableLibraryCategories: ref({}),
      });
      expect(wrapper.findAll('[data-test="category-pill"]').length).toBe(0);
    });
  });
});

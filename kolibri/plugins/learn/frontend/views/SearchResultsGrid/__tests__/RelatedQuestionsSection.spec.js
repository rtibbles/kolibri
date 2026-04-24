import { shallowMount } from '@vue/test-utils';
import RelatedQuestionsSection from '../RelatedQuestionsSection.vue';

const mockQuestions = [
  'What is a square root of a non-perfect square?',
  'How do I calculate square root by hand?',
  'What are the properties of square roots?',
];

function makeWrapper(propsData = {}) {
  return shallowMount(RelatedQuestionsSection, {
    propsData: {
      questions: [],
      ...propsData,
    },
  });
}

describe('RelatedQuestionsSection', () => {
  it('renders nothing when no questions', () => {
    const wrapper = makeWrapper();
    expect(wrapper.find('[data-test="related-questions-section"]').exists()).toBe(false);
  });

  it('renders section when questions are provided', () => {
    const wrapper = makeWrapper({ questions: mockQuestions });
    expect(wrapper.find('[data-test="related-questions-section"]').exists()).toBe(true);
  });

  it('renders a question chip for each question', () => {
    const wrapper = makeWrapper({ questions: mockQuestions });
    const chips = wrapper.findAll('[data-test="related-question-chip"]');
    expect(chips.length).toBe(3);
  });

  it('emits selectQuestion when a chip is clicked', async () => {
    const wrapper = makeWrapper({ questions: mockQuestions });
    const chip = wrapper.findAll('[data-test="related-question-chip"]').at(0);
    chip.vm.$emit('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('selectQuestion')).toBeTruthy();
    expect(wrapper.emitted('selectQuestion')[0][0]).toBe(mockQuestions[0]);
  });

  it('renders section header', () => {
    const wrapper = makeWrapper({ questions: mockQuestions });
    expect(wrapper.text()).toContain('Related questions');
  });
});

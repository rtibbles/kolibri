import { shallowMount } from '@vue/test-utils';
import SuggestedQuestionChips from '../SuggestedQuestionChips.vue';

function makeWrapper(propsData = {}) {
  return shallowMount(SuggestedQuestionChips, {
    propsData: {
      questions: [
        'What are numerators?',
        'What are denominators?',
        'How do I add fractions?',
      ],
      ...propsData,
    },
  });
}

describe('SuggestedQuestionChips', () => {
  it('renders chips for each question', () => {
    const wrapper = makeWrapper();
    const chips = wrapper.findAll('[data-test="question-chip"]');
    expect(chips.length).toBe(3);
  });

  it('displays question text in chip attributes', () => {
    const wrapper = makeWrapper();
    const chips = wrapper.findAll('[data-test="question-chip"]');
    // Stubbed KButton receives text as prop
    expect(chips.at(0).attributes('text')).toBe('What are numerators?');
    expect(chips.at(1).attributes('text')).toBe('What are denominators?');
  });

  it('emits selectQuestion with question text when chip is clicked', async () => {
    const wrapper = makeWrapper();
    const chips = wrapper.findAll('[data-test="question-chip"]');
    chips.at(0).vm.$emit('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('selectQuestion')).toBeTruthy();
    expect(wrapper.emitted('selectQuestion')[0]).toEqual(['What are numerators?']);
  });

  it('renders nothing when questions array is empty', () => {
    const wrapper = makeWrapper({ questions: [] });
    expect(wrapper.findAll('[data-test="question-chip"]').length).toBe(0);
  });

  it('renders nothing when questions prop is not provided', () => {
    const wrapper = shallowMount(SuggestedQuestionChips);
    expect(wrapper.findAll('[data-test="question-chip"]').length).toBe(0);
  });
});

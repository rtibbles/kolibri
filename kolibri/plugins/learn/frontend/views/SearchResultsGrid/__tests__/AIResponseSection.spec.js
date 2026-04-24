import { shallowMount } from '@vue/test-utils';
import AIResponseSection from '../AIResponseSection.vue';

function makeWrapper(propsData = {}) {
  return shallowMount(AIResponseSection, {
    propsData: {
      messages: [],
      categoryChips: [],
      ...propsData,
    },
  });
}

describe('AIResponseSection', () => {
  it('renders nothing when no messages', () => {
    const wrapper = makeWrapper();
    expect(wrapper.find('[data-test="ai-response-section"]').exists()).toBe(false);
  });

  it('renders messages when provided', () => {
    const wrapper = makeWrapper({
      messages: [
        'You can calculate a square root by finding the number that, when multiplied by itself, equals the original number.',
      ],
    });
    expect(wrapper.find('[data-test="ai-response-section"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('You can calculate a square root');
  });

  it('renders multiple messages', () => {
    const wrapper = makeWrapper({
      messages: ['First message.', 'Second message.'],
    });
    const messageDivs = wrapper.findAll('[data-test="ai-message"]');
    expect(messageDivs.length).toBe(2);
  });

  it('renders category chips when provided', () => {
    const wrapper = makeWrapper({
      messages: ['Some AI response'],
      categoryChips: [
        { label: 'Exponents', value: 'exponents_id' },
        { label: 'Algebra', value: 'algebra_id' },
      ],
    });
    const chips = wrapper.findAll('[data-test="category-chip"]');
    expect(chips.length).toBe(2);
  });

  it('emits selectCategory when a category chip is clicked', async () => {
    const wrapper = makeWrapper({
      messages: ['Some response'],
      categoryChips: [{ label: 'Exponents', value: 'exponents_id' }],
    });
    const chip = wrapper.findAll('[data-test="category-chip"]').at(0);
    chip.vm.$emit('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('selectCategory')).toBeTruthy();
    expect(wrapper.emitted('selectCategory')[0][0]).toEqual({
      label: 'Exponents',
      value: 'exponents_id',
    });
  });

  it('has a dismiss button', () => {
    const wrapper = makeWrapper({
      messages: ['Some response'],
    });
    expect(wrapper.find('[data-test="dismiss-button"]').exists()).toBe(true);
  });

  it('hides content when dismiss button is clicked', async () => {
    const wrapper = makeWrapper({
      messages: ['Some response'],
    });
    const dismissBtn = wrapper.find('[data-test="dismiss-button"]');
    dismissBtn.vm.$emit('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-test="ai-response-section"]').exists()).toBe(false);
  });
});

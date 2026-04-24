import { shallowMount } from '@vue/test-utils';
import HorizontalCardRow from '../HorizontalCardRow.vue';

const mockItems = [
  { id: 'node-1', title: 'Item 1' },
  { id: 'node-2', title: 'Item 2' },
  { id: 'node-3', title: 'Item 3' },
  { id: 'node-4', title: 'Item 4' },
];

function makeWrapper(propsData = {}) {
  return shallowMount(HorizontalCardRow, {
    propsData: {
      items: [],
      ...propsData,
    },
    scopedSlots: {
      default: '<div class="test-card" slot-scope="{ item }">{{ item.title }}</div>',
    },
  });
}

describe('HorizontalCardRow', () => {
  it('renders the scroll container', () => {
    const wrapper = makeWrapper({ items: mockItems });
    expect(wrapper.find('[data-testid="scroll-container"]').exists()).toBe(true);
  });

  it('renders nothing when items is empty', () => {
    const wrapper = makeWrapper({ items: [] });
    expect(wrapper.find('[data-testid="scroll-container"]').exists()).toBe(false);
  });

  it('uses scoped slot to render items', () => {
    const wrapper = makeWrapper({ items: mockItems });
    expect(wrapper.text()).toContain('Item 1');
    expect(wrapper.text()).toContain('Item 2');
  });

  it('renders navigation buttons', () => {
    const wrapper = makeWrapper({ items: mockItems });
    expect(wrapper.find('[data-testid="scroll-left-button"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="scroll-right-button"]').exists()).toBe(true);
  });
});

import { shallowMount } from '@vue/test-utils';
import MoreToExploreSection from '../MoreToExploreSection.vue';

const mockGroups = [
  {
    label: 'square root equations',
    count: 24,
    items: [
      { id: 'n1', title: 'Item 1' },
      { id: 'n2', title: 'Item 2' },
    ],
  },
  {
    label: 'Square root examples',
    count: 10,
    items: [
      { id: 'n3', title: 'Item 3' },
    ],
  },
];

function makeWrapper(propsData = {}) {
  return shallowMount(MoreToExploreSection, {
    propsData: {
      groups: [],
      ...propsData,
    },
  });
}

describe('MoreToExploreSection', () => {
  it('renders nothing when groups is empty', () => {
    const wrapper = makeWrapper();
    expect(wrapper.find('[data-test="more-to-explore"]').exists()).toBe(false);
  });

  it('renders section when groups are provided', () => {
    const wrapper = makeWrapper({ groups: mockGroups });
    expect(wrapper.find('[data-test="more-to-explore"]').exists()).toBe(true);
  });

  it('renders a section header', () => {
    const wrapper = makeWrapper({ groups: mockGroups });
    expect(wrapper.text()).toContain('More to explore');
  });

  it('renders a group for each category', () => {
    const wrapper = makeWrapper({ groups: mockGroups });
    const groups = wrapper.findAll('[data-test="explore-group"]');
    expect(groups.length).toBe(2);
  });

  it('renders group label and count', () => {
    const wrapper = makeWrapper({ groups: mockGroups });
    const firstGroup = wrapper.findAll('[data-test="explore-group"]').at(0);
    expect(firstGroup.text()).toContain('square root equations');
    expect(firstGroup.text()).toContain('24');
  });

  it('renders HorizontalCardRow for each group', () => {
    const wrapper = makeWrapper({ groups: mockGroups });
    const rows = wrapper.findAllComponents({ name: 'HorizontalCardRow' });
    expect(rows.length).toBe(2);
  });
});

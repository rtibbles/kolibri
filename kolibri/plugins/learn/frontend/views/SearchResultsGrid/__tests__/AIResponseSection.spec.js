import { render, screen, fireEvent } from '@testing-library/vue';
import AIResponseSection from '../AIResponseSection.vue';

function renderComponent(props = {}) {
  return render(AIResponseSection, {
    props: {
      messages: [],
      categoryChips: [],
      ...props,
    },
  });
}

describe('AIResponseSection', () => {
  it('renders nothing when no messages', () => {
    renderComponent();
    expect(screen.queryByTestId('ai-response-section')).not.toBeInTheDocument();
  });

  it('renders messages when provided', () => {
    const message = 'A sample AI-generated response message.';
    renderComponent({ messages: [message] });
    expect(screen.getByTestId('ai-response-section')).toBeInTheDocument();
    expect(screen.getByTestId('ai-message')).toHaveTextContent(new RegExp(message));
  });

  it('renders multiple messages', () => {
    renderComponent({
      messages: ['First message.', 'Second message.'],
    });
    expect(screen.getAllByTestId('ai-message')).toHaveLength(2);
  });

  it('renders category chips when provided', () => {
    renderComponent({
      messages: ['Some AI response'],
      categoryChips: [
        { label: 'Exponents', value: 'exponents_id' },
        { label: 'Algebra', value: 'algebra_id' },
      ],
    });
    expect(screen.getAllByTestId('category-chip')).toHaveLength(2);
  });

  it('emits selectCategory when a category chip is clicked', async () => {
    const { emitted } = renderComponent({
      messages: ['Some response'],
      categoryChips: [{ label: 'Exponents', value: 'exponents_id' }],
    });
    await fireEvent.click(screen.getByTestId('category-chip'));
    expect(emitted()).toHaveProperty('selectCategory');
    expect(emitted().selectCategory[0][0]).toEqual({
      label: 'Exponents',
      value: 'exponents_id',
    });
  });

  it('renders markdown bold in messages', () => {
    const { container } = renderComponent({
      messages: ['This is **bold** text.'],
    });
    const strong = container.querySelector('[data-testid="ai-message"] strong');
    expect(strong).not.toBeNull();
    expect(strong).toHaveTextContent('bold');
  });

  it('renders LaTeX math in messages', () => {
    const { container } = renderComponent({
      messages: ['The formula is \\(x^2 + y^2 = z^2\\).'],
    });
    const katex = container.querySelector('[data-testid="ai-message"] .katex');
    expect(katex).not.toBeNull();
  });
});

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
  test('renders nothing when no messages', () => {
    renderComponent();
    expect(screen.queryByTestId('ai-response-section')).not.toBeInTheDocument();
  });

  test('renders messages when provided', () => {
    renderComponent({
      messages: [
        'You can calculate a square root by finding the number that, when multiplied by itself, equals the original number.',
      ],
    });
    expect(screen.getByTestId('ai-response-section')).toBeInTheDocument();
    expect(screen.getByText(/You can calculate a square root/)).toBeInTheDocument();
  });

  test('renders multiple messages', () => {
    renderComponent({
      messages: ['First message.', 'Second message.'],
    });
    expect(screen.getAllByTestId('ai-message')).toHaveLength(2);
  });

  test('renders category chips when provided', () => {
    renderComponent({
      messages: ['Some AI response'],
      categoryChips: [
        { label: 'Exponents', value: 'exponents_id' },
        { label: 'Algebra', value: 'algebra_id' },
      ],
    });
    expect(screen.getAllByTestId('category-chip')).toHaveLength(2);
  });

  test('emits selectCategory when a category chip is clicked', async () => {
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

  test('has a dismiss button', () => {
    renderComponent({ messages: ['Some response'] });
    expect(screen.getByTestId('dismiss-button')).toBeInTheDocument();
  });

  test('hides content when dismiss button is clicked', async () => {
    renderComponent({ messages: ['Some response'] });
    await fireEvent.click(screen.getByTestId('dismiss-button'));
    expect(screen.queryByTestId('ai-response-section')).not.toBeInTheDocument();
  });

  test('renders markdown bold in messages', () => {
    const { container } = renderComponent({
      messages: ['This is **bold** text.'],
    });
    const strong = container.querySelector('[data-testid="ai-message"] strong');
    expect(strong).not.toBeNull();
    expect(strong.textContent).toBe('bold');
  });

  test('renders LaTeX math in messages', () => {
    const { container } = renderComponent({
      messages: ['The formula is \\(x^2 + y^2 = z^2\\).'],
    });
    const katex = container.querySelector('[data-testid="ai-message"] .katex');
    expect(katex).not.toBeNull();
  });
});

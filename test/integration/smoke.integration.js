describe('Kolibri', () => {
  it('should go to the home page', async () => {
    await page.goto('http://127.0.0.1:8000');
    await expect(page).toMatch('Kolibri');
  });
});

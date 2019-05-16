describe('Kolibri', () => {
  it('should go to the home page', async () => {
    await page.goto('http://127.0.0.1:8000');
    await expect(page).toMatch('Kolibri');
  });
  it('should redirect to the user page', async () => {
    await page.goto('http://127.0.0.1:8000');
    await expect(page.url()).toEqual(expect.stringContaining('/user'));
    await page.waitForSelector('div#username input.ui-textbox-input', { timeout: 10000 });
    await page.screenshot({ path: 'example.png' });
  });
});

import { expect, test } from '@playwright/test';

test.describe('ORION dashboard', () => {
  test('renders header, ticker and globe', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('app-header')).toBeVisible();
    await expect(page.getByTestId('globe-container')).toBeVisible();
    await expect(page.getByTestId('dashboard')).toBeVisible();
  });

  test('region pills switch market and update panels', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('region-US').click();
    await expect(page.getByTestId('region-US')).toHaveAttribute(
      'aria-selected', 'true');
    await expect(page.getByTestId('top-movers')).toBeVisible();
  });

  test('globe renders an interactive canvas (markers are WebGL, not DOM)',
    async ({ page }) => {
      await page.goto('/');
      const container = page.getByTestId('globe-container');
      await expect(container).toBeVisible();
      await expect(container.locator('canvas')).toHaveCount(1);
    });

  test('symbol search returns hits', async ({ page }) => {
    await page.goto('/');
    const search = page.getByTestId('symbol-search');
    await search.fill('NVDA');
    await expect(page.locator('ul >> text=NVDA').first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test('chart panel handles empty state without crash', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('chart-panel')).toBeVisible();
  });
});

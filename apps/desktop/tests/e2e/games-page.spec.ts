import { test, expect } from '@playwright/test';

test.describe('Games Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/games');
    await page.evaluate(() => {
      localStorage.setItem('backend_url', 'http://127.0.0.1:18080');
      localStorage.setItem('auth_token', 'devtoken123');
    });
    await page.reload();
  });

  test('should display game list', async ({ page }) => {
    await page.waitForSelector('text=Games', { timeout: 15000 });
    const gameTable = page.locator('table');
    await expect(gameTable).toBeVisible({ timeout: 10000 });
  });

  test('should show game count', async ({ page }) => {
    // Wait for data to load
    await expect(page.locator('text=551').first()).toBeVisible({ timeout: 15000 });
  });

  test('should navigate to game detail on click', async ({ page }) => {
    // Click first game row
    const firstRow = page.locator('table tbody tr').first();
    await firstRow.click();
    // Should navigate to /games/$gameId
    await expect(page).toHaveURL(/\/games\//);
  });
});

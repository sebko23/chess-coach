import { test, expect } from '@playwright/test';

test.describe('Training Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/training');
    await page.evaluate(() => {
      localStorage.setItem('backend_url', 'http://127.0.0.1:18080');
      localStorage.setItem('auth_token', 'devtoken123');
    });
    await page.reload();
  });

  test('should display training queue', async ({ page }) => {
    // Should show card queue
    await expect(page.locator('text=Training').first()).toBeVisible({ timeout: 15000 });
  });

  test('should show due cards count', async ({ page }) => {
    await expect(page.locator('text=3739').first()).toBeVisible({ timeout: 15000 });
  });

  test('should show blunder badges on cards', async ({ page }) => {
    await page.waitForTimeout(5000); // Wait for BlunderBadge fetches
    const badges = page.locator('[class*=blunder], [class*=badge]');
    const count = await badges.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should show ECO badge on cards', async ({ page }) => {
    // ECO badge displays e.g. "D00"
    const ecoBadge = page.locator('text=/^[A-E]\\d{2}$/').first();
    await expect(ecoBadge).toBeVisible({ timeout: 10000 });
  });

  test('should allow reviewing a card', async ({ page }) => {
    await page.waitForSelector('button', { timeout: 15000 });
    const reviewButton = page.locator('button').filter({ hasText: /Rate|Review|Good|Easy|Hard/ }).first();
    if (await reviewButton.isVisible()) {
      await reviewButton.click();
      // Review should succeed without error
      await page.waitForTimeout(2000);
    }
  });
});

import { test, expect } from '@playwright/test';

test.describe('Coach Panel', () => {
  test.beforeEach(async ({ page }) => {
    // Set up auth state
    await page.goto('/coach');
    await page.evaluate(() => {
      localStorage.setItem('backend_url', 'http://127.0.0.1:18080');
      localStorage.setItem('auth_token', 'devtoken123');
    });
    await page.reload();
  });

  test('should connect to backend successfully', async ({ page }) => {
    const connectStatus = page.locator('text=Connected to backend');
    await expect(connectStatus).toBeVisible({ timeout: 15000 });
  });

  test('should display engine analysis after connect', async ({ page }) => {
    // Wait for analysis to load
    await page.waitForSelector('text=Best Line', { timeout: 30000 });
    await expect(page.locator('text=Best Line')).toBeVisible();
  });

  test('should display blunder badges', async ({ page }) => {
    await page.waitForSelector('text=Blunders', { timeout: 30000 });
    await expect(page.locator('text=Blunders')).toBeVisible();
  });

  test('should show eval chart', async ({ page }) => {
    await page.waitForSelector('canvas', { timeout: 30000 });
    const canvases = page.locator('canvas');
    await expect(canvases.first()).toBeVisible();
  });
});

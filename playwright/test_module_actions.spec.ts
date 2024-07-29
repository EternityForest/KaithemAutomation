import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('http://localhost:8002/');
  await page.getByRole('link', { name: '󱒕 Modules' }).click();
  await page.getByRole('link', { name: '󰐕 Add' }).click();
  
  await page.getByLabel('Username:').click();
  await page.getByLabel('Username:').fill('admin');
  await page.getByLabel('Username:').press('Tab');
  await page.getByLabel('Password:').fill('test-admin-password');
  await page.getByLabel('Password:').press('Enter');
  await page.getByLabel('Name of New Module').click();
  await page.getByLabel('Name of New Module').fill('foo');
  await page.getByRole('button', { name: 'Submit' }).click();
  await page.locator('summary').click();
  await page.frameLocator('details iframe').getByRole('button', { name: 'Add a link to the nav bar' }).click();
});
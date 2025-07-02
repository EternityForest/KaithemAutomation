import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('http://localhost:8002/');
  await page.getByRole('link', { name: '󰢻 Tools' }).click();
  await page.getByRole('link', { name: '󰘥 Help' }).click();
  await page.getByRole('link', { name: 'About Kaithem' }).click();
  await expect(page.getByRole('main')).toContainText('Disks');
  await page.getByRole('heading', { name: 'Python Path' }).click();
  await page.getByRole('link', { name: '󰢻 Tools' }).click();
  await page.getByRole('link', { name: '󰘥 Help' }).click();
  await page.getByText('General About Kaithem Online').click();
  await page.getByRole('link', { name: 'General Documentation' }).click();
  await expect(page.locator('#spanidintrospanintroduction')).toContainText('Introduction');
  await page.getByRole('link', { name: '󰢻 Tools' }).click();
  await page.getByRole('link', { name: '󰘥 Help' }).click();
  await page.getByRole('link', { name: 'Change Log' }).click();
  await expect(page.locator('#changelog')).toContainText('Change Log');
  await page.getByRole('link', { name: '󰢻 Tools' }).click();
  await page.getByRole('link', { name: '󰘥 Help' }).click();
  await page.getByRole('link', { name: 'Math constants, knots, and' }).click();
  await expect(page.locator('#mathdata')).toContainText('Math Data');
});
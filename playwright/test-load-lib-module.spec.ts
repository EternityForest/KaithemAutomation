import { test, expect } from '@playwright/test';
import { login, logout, deleteModule } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'Library' }).click();
    await page.locator('dt').filter({ hasText: 'Examples Load' }).getByRole('button').click()
    
    await page.goto('http://localhost:8002/modules');

    await page.getByRole('link', { name: 'Examples' }).click();
    await page.getByRole('link', { name: 'Time Event' }).click();
    await expect(page.locator('h2')).toContainText('Event Time Event of module Examples');
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'Examples' }).click();
    await page.getByRole('link', { name: '󰐊 Go to page' }).nth(2).click();
    await expect(page.locator('section')).toContainText('Here\'s a counter! 1');
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'Examples' }).click();

    await deleteModule(page, 'Examples');

    await logout(page);

});
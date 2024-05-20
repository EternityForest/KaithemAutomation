import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
    /*
    Logs in, creates a module, creates a page, and creates an event
    Tests basic fuctions, then renames them both and confirms they still work.
    Delete module then log out.
    */
    await page.goto('http://localhost:8002/');
    await page.getByRole('link', { name: 'Login' }).click();
    await page.getByLabel('Username:').click();
    await page.getByLabel('Username:').fill('admin');
    await page.getByLabel('Username:').press('Tab');
    await page.getByLabel('Password:').fill('test-admin-password');
    await page.getByRole('button', { name: 'Login as Registered User' }).click();
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('PlaywrightBasicModuleFeatures');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: 'Page' }).click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('p1');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.locator('.ace_content').first().fill('foo = "123"\n\n');
    await page.locator('label:nth-child(4) > div > .ace_scroller > .ace_content').fill('setup = "234"\n\n');
    await page.locator('div').filter({ hasText: '{% extends "pagetemplate.j2.' }).nth(2).click();
    await page.locator('div').filter({ hasText: '{% extends "pagetemplate.j2.' }).nth(2).fill('    {{foo}}{{setup}}567\n\n');
    await page.getByRole('button', { name: 'Save and go to page' }).click();
    await expect(page.getByText('p1 Content here')).toContainText('123234567');
    await expect(page.getByRole('heading')).toContainText('p1');
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'PlaywrightBasicModuleFeatures' }).click();
    await expect(page.locator('h3')).toContainText('p1 (page)');
    await page.getByRole('link', { name: 'Event' }).click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('e1');
    await page.getByRole('button', { name: 'Submit' }).click();
    await expect(page.getByRole('paragraph')).toContainText('This event has not ran since it loaded.');
    await page.locator('#triggerbox').click({
        clickCount: 3
    });
    await page.locator('#triggerbox').fill('True');
    await page.getByRole('button', { name: 'Save Changes' }).click();
    await expect(page.locator('dl')).toContainText('ago');
    await page.getByRole('link', { name: 'e1 (event)' }).click();
    await expect(page.getByRole('paragraph')).toContainText('ago');
    await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures#resources");

    await page.getByRole('link', { name: 'Move' }).nth(1).click();
    await page.getByLabel('New Name').click();
    await page.getByLabel('New Name').fill('p1_new');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: 'Go to page' }).click();
    await page.locator('html').click();
    await expect(page.getByText('p1 Content here')).toContainText('123234567');
    await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures#resources");

    await page.getByRole('link', { name: 'p1_new (page)' }).click();
    await expect(page.getByRole('heading')).toContainText('PlaywrightBasicModuleFeatures: p1_new');
    await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures#resources");
    await page.getByRole('link', { name: 'Move' }).first().click();
    await page.getByLabel('New Name').click();
    await page.getByLabel('New Name').fill('e1_new');
    await page.getByRole('button', { name: 'Submit' }).click();
    await expect(page.locator('dl')).toContainText('ago');
    await page.getByRole('link', { name: 'e1_new (event)' }).click();
    await expect(page.locator('h2')).toContainText('e1_new');
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'Delete' }).click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('PlaywrightBasicModuleFeatures');
    await page.getByRole('button', { name: 'Submit' }).click();
    await expect(page.getByRole('heading')).toContainText('Modules');
    await page.getByRole('button', { name: 'Logout(admin)' }).click();
});
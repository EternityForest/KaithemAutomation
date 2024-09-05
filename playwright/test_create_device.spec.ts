import { test, expect } from '@playwright/test';
import { login, logout, makeModule, deleteModule } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);
    // Make a module to put the device in

    await makeModule(page, 'devmodule');

    // Make a device
    await page.getByTestId('add-resource-button').click();
    await page.getByTestId('add-device').click();
    await page.getByLabel('Target Resource Name:').click();
    await page.getByLabel('Target Resource Name:').fill('testdevice');
    await page.getByText('Target Module: Target').click();
    await page.getByPlaceholder('Click for dropdown').click();
    await page.getByPlaceholder('Click for dropdown').fill('DemoDevice');
    await page.getByRole('button', { name: 'Create' }).click();
    await page.getByRole('button', { name: 'Submit' }).click();

    // Should be on devices page now, make sure it exists and works
    await expect(page.locator('section')).toContainText('testdevice');
    await expect(page.locator('section')).toContainText('random');

    // Go to the page for that specific device
    await page.getByRole('link', { name: 'testdevice', exact: true }).click();

    //Make sure we can set settings
    await page.locator('b').filter({ hasText: 'Settings' }).locator('i').click();
    await page.locator('[id="property_device\\.fixed_number_multiplier"]').click();
    await page.locator('[id="property_device\\.fixed_number_multiplier"]').fill('2');
    await page.getByRole('button', { name: 'Save settings' }).click();
    await page.getByRole('link', { name: 'testdevice', exact: true }).click();
    await page.locator('summary').filter({ hasText: 'Settings' }).click();
    await expect(page.locator('[id="property_device\\.fixed_number_multiplier"]')).toHaveValue('2');

    // Make sure we can see it in the modules page
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.locator('summary').filter({ hasText: 'devmodule' }).click();
    await page.getByRole('link', { name: 'devmodule' }).click();
    await expect(page.getByRole('link', { name: 'testdevice' })).toBeVisible()

    // Delete it

    await page.getByLabel('Delete').click()

    await page.getByRole('button', { name: 'Submit' }).click();
    
    await deleteModule(page, 'devmodule');

    await logout(page);
});
import { test, expect } from '@playwright/test';
import { login, logout, deleteModule } from './util';

test('test', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: '󰐕 Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('testpageoptions');
    await page.getByRole('button', { name: 'Submit' }).click();

    await page.getByTestId('add-page').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('test_options');
    await page.getByRole('button', { name: 'Submit' }).click();

    // Set theme to scrapbook
    await page.getByText('Settings', { exact: true }).click();
    await page.getByLabel('Theme').click();
    await page.getByLabel('Theme').fill('scrapbook');

    // Set no template engine
    await page.getByLabel('Template Engine jinja2').selectOption('none');

    // Save
    await page.getByRole('button', { name: 'Submit' }).click();

    // Go to the page
    await page.getByRole('link', { name: '󰖟 test_options (page)' }).click();

    // Make sure we can see the options
    await page.getByText('Settings', { exact: true }).click();
    await expect(page.getByLabel('Theme')).toHaveValue('scrapbook');
    await expect(page.getByLabel('Template Engine jinja2')).toHaveValue('none');

    // Actually go to pge
    await page.getByRole('button', { name: 'Save and go to page' }).click();

    // We turned off template rendering, so this should have raw template syntax
    await expect(page.getByText('{% endblock %}')).toBeVisible();

    // Back to page editor
    await page.goBack()

    // Back to jinja2, all permissions
    await page.getByText('Settings', { exact: true }).click();

    await page.getByLabel('Template Engine jinja2').selectOption('jinja2');
    await page.getByText('Require Permissions').click();
    await page.getByLabel('__all_permissions__').check();
    await page.getByRole('button', { name: 'Save and go to page' }).click();
    await page.goBack()
    
    
    await expect(page.getByLabel('Template Engine jinja2')).toHaveValue('jinja2');

    await page.getByText('Require Permissions').click();
    await expect(page.getByLabel('__all_permissions__')).toBeChecked();


    // Disallow POST, set alt banner text, set xss origins
    await page.getByText('Settings', { exact: true }).click();
    await page.getByLabel('Allow POST').uncheck();
    await page.getByLabel('Alt Top Banner Text').click();
    await page.getByLabel('Alt Top Banner Text').fill('foo');
    await page.getByLabel('XSS Origins').click();
    await page.getByLabel('XSS Origins').fill('example');

    await page.getByRole('button', { name: 'Submit' }).click();


    await page.getByRole('link', { name: '󰖟 test_options (page)' }).click();
    await page.getByText('Settings', { exact: true }).click();

    await expect(page.getByLabel('Allow POST')).not.toBeChecked();
    await expect(page.getByLabel('Alt Top Banner Text')).toHaveValue('foo');

    await expect(page.getByLabel('XSS Origins')).toHaveValue('example');


    await deleteModule(page, 'testpageoptions');
    await logout(page);

})
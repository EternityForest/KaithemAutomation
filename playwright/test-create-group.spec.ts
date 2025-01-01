import { test, expect } from '@playwright/test';
import { login, logout, login_as } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);

    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰡉 Users and Groups' }).click();
    await page.getByRole('link', { name: 'Add New Group' }).click();
    await page.getByRole('textbox').click();
    await page.getByRole('textbox').fill('testgroup');
    await page.getByRole('button', { name: 'Create Group' }).click();

    // Add view status permission and maxbyttes limit
    await page.getByRole('link', { name: 'testgroup' , exact: true}).click();
    await page.locator('input[name="Permissionview_status"]').check();
    await page.locator('input[name="maxbytes"]').click();
    await page.locator('input[name="maxbytes"]').fill('123456');
    await page.getByRole('button', { name: 'Save Changes' }).click();

    // Check group settings
    await page.getByRole('link', { name: 'testgroup' , exact: true}).click();
    await page.locator('input[name="maxbytes"]').click();
    await expect(page.locator('input[name="maxbytes"]')).toHaveValue('123456');
    await page.getByRole('link', { name: 'Tools' }).click();
    await page.getByRole('link', { name: 'Users and Groups' }).click();
    await expect(page.getByRole('main')).toContainText('testgroup');

    // Make user with password 12345
    await page.getByRole('link', { name: 'Add New User' }).click();
    await page.getByLabel('Username').click();
    await page.getByLabel('Username').fill('testgroupuser');
    await page.getByLabel('Password', { exact: true }).click();
    await page.getByLabel('Password',  { exact: true }).fill('12345');

    await page.getByRole('button', { name: 'Submit' }).click();



    // Try changing password from the admin panel, add to test group
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰡉 Users and Groups' }).click();



    await page.getByRole('link', { name: 'testgroupuser' }).click();
    await page.locator('input[name="Grouptestgroup"]').check();

    await page.getByLabel('(Leave blank=don\'t change)').click();
    await page.getByLabel('(Leave blank=don\'t change)').fill('123');
    await page.getByLabel('Retype password').click();
    await page.getByLabel('Retype password').fill('123');
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await logout(page);
    await login_as(page, 'testgroupuser', '123');
    

    // Should be logged in
    await expect(page.getByRole('banner')).toContainText('Logout');
    await page.getByRole('link', { name: 'Tools' }).click();
    await page.getByRole('link', { name: 'My Account' }).click();

    // But going to the account page fails due to lacking
    // The own account settings permission
    await expect(page.locator('h2')).toContainText('Please Log In');

    // So we login as admin when redirected to the login
    await login(page);

    // Now we can give test group the own_account_settings permission
    await page.getByRole('link', { name: 'Tools' }).click();
    await page.getByRole('link', { name: 'Users and Groups' }).click();
    await page.getByRole('link', { name: 'testgroup', exact: true }).click();
    await page.locator('input[name="Permissionown_account_settings"]').check();
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await logout(page);


    // Log back in as test user
    await login_as(page, 'testgroupuser', '123');

    // Should now be able to go to account settings
    await page.getByRole('link', { name: 'Tools' }).click();
    await page.getByRole('link', { name: 'My Account' }).click();

    // Change password to 1234
    await page.locator('input[name="old"]').click();
    await page.locator('input[name="old"]').fill('123');
    await page.locator('input[name="new"]').click();
    await page.locator('input[name="new"]').fill('1234');
    await page.locator('input[name="new2"]').click();
    await page.locator('input[name="new2"]').fill('1234');
    await page.getByRole('button', { name: 'Change Password' }).click();

    // Logout and try password
    await logout(page);

    await login_as(page, 'testgroupuser', '1234');

    // New password should work
    await expect(page.getByRole('banner')).toContainText('Logout');

    
    await logout(page);

    // Log back in as admin and delete group and user
    await login(page);


    await page.getByRole('link', { name: 'Tools' }).click();
    await page.getByRole('link', { name: 'Users and Groups' }).click();
    await page.getByRole('link', { name: 'Delete Group' }).click();
    await page.getByRole('textbox').click();
    await page.getByRole('textbox').fill('testgroup');
    await page.getByRole('button', { name: 'Delete(cannot be undone)' }).click();
    await page.getByRole('link', { name: 'testgroupuser' }).click();
    await page.getByRole('button', { name: 'Save Changes' }).click();
    await page.getByRole('link', { name: 'Delete User' }).click();
    await page.getByLabel('User').click();
    await page.getByLabel('User').fill('testgroupuser');
    await page.getByRole('button', { name: 'Submit' }).click();
    
    await logout(page);

});
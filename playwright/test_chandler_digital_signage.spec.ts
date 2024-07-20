import { test, expect } from '@playwright/test';
import { login, logout, makeModule, deleteModule, makeTagPoint } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);

    await page.getByRole('link', { name: '󱒕 Modules' }).click();

    //Make a media folder and put a png there

    makeModule(page, 'test_digital_signage');

    await page.getByRole('button', { name: 'Add Resource' }).click();
    await page.getByTestId('add-folder').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('media');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: '󰉖 media' }).click();
    await page.getByRole('button', { name: 'Add Resource' }).click();

    await page.getByTestId('add-file').click();
    await page.locator('#upload').click();
    await page.locator('#upload').setInputFiles('badges/linux.png');
    await page.getByRole('button', { name: 'Upload' }).click();


    await page.getByRole('link', { name: 'test_digital_signage' }).click();
    await page.getByRole('button', { name: 'Add Resource' }).click();

    await page.getByTestId('add-chandler_board').click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill('board1');
    await page.getByRole('button', { name: 'Submit' }).click();


    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'test_digital_signage' }).click();
    await page.getByRole('link', { name: '󰏬 Editor' }).click();


    await page.getByPlaceholder('New group name').dblclick();
    await page.getByPlaceholder('New group name').fill('signage');
    await page.getByTestId('add-group-button').click();

    //Set the slide for the cue
    await page.getByRole('button', { name: 'signage' }).click();
    await page.getByRole('button', { name: 'Media' }).click();
    await page.locator('#cueMediaDialog').getByText('<TOP DIRECTORY>').click()
    await page.locator('#cueMediaDialog').getByText('/dev/shm/kaithem_test_env/modules/data/test_digital_signage/__filedata__/media/').click();
    await page.getByRole('button', { name: 'Set(slide)' }).click();
    
    //Use the slideshow preview window
    await expect(page.getByRole('article')).toContainText('(slideshow)');
    await page.locator('summary').filter({ hasText: '(slideshow)' }).click();
    await expect(page.frameLocator('article iframe').getByRole('img')).toBeVisible();
    await expect(page.getByPlaceholder('New cue name')).toBeVisible();
    await page.getByPlaceholder('New cue name').click();
    await page.getByPlaceholder('New cue name').fill('c2');
    await page.getByRole('button', { name: '󰐕 Add Cue' }).click();
    await page.getByRole('button', { name: 'Go' }).nth(4).click();

    await expect(page.getByRole('article')).toContainText('c2');

    // TODO: Make sure the slide actually changes
    
    deleteModule(page, 'test_digital_signage');

    await logout(page);
});
import { test, expect } from '@playwright/test';
import { login, logout, makeModule, deleteModule, sleep } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);

    await makeModule(page, 'testcue');

    await page.getByTestId('add-resource-button').click();

    await page.getByTestId('add-chandler_board').click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill('testcue');
    await page.getByRole('button', { name: 'Submit' }).click();



    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'testcue' }).click();
    await page.getByRole('link', { name: '󰏬 Editor' }).click();
    await page.getByPlaceholder('New group name').click();
    await page.getByTestId('add-group-button').click();
    await page.getByRole('button', { name: '󰅖 Close' }).click();
    await page.getByPlaceholder('New group name').click();
    await page.getByPlaceholder('New group name').fill('tst');
    await sleep(200);
    await page.getByTestId('add-group-button').click();
    await page.getByRole('button', { name: 'tst' }).click();
    await page.getByTestId('cue-media-dialog-button').click();
    await page.getByLabel('Sound start s into file.').click();
    await page.getByLabel('Sound start s into file.').fill('1');
    await page.getByLabel('Media Speed').click();
    await page.getByLabel('Media Speed').fill('1.2');
    await page.getByLabel('Windup').click();
    await page.getByLabel('Windup').fill('0.1');
    await page.getByLabel('Winddown').click();
    await page.getByLabel('Winddown').fill('0.3');
    await page.getByLabel('Device Play media file in web').click();
    await page.getByLabel('Device Play media file in web').fill('groupwebplayer');
    await page.getByLabel('Relative length').click({
        button: 'right'
    });
    await expect(page.getByLabel('Relative length')).not.toBeChecked();
    await page.getByLabel('Relative length').check();
    await page.getByLabel('Fade sound after end').click();
    await page.getByLabel('Fade sound after end').fill('0.6');
    await page.getByLabel('Sound fadein:').click();
    await page.getByLabel('Sound fadein:').fill('0.7');
    await page.getByLabel('Cue Volume').click();
    await page.getByLabel('Cue Volume').fill('0.8');
    await page.getByLabel('Loops').click();
    await page.getByLabel('Loops').fill('8');
    await page.getByTestId('media-browser-container').getByText('<TOP DIRECTORY>').click();
    await page.getByTestId('media-browser-container').getByText('/home/daniel/Projects/').click();
    await page.getByTestId('media-browser-container').getByText('/home/daniel/Projects/KaithemAutomation/kaithem/data/static/img/').click();
    await page.getByTestId('media-browser-container').getByText('/home/daniel/Projects/KaithemAutomation/kaithem/data/static/img/16x9/').click();
    await page.locator('tr:nth-child(3) > td:nth-child(2) > button:nth-child(6)').click();
    await page.getByTestId('close-cue-media').click();
    await page.getByTestId('close-group').click();

    // Verify
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'testcue' }).click();
    await page.getByRole('link', { name: '󰏬 Editor' }).click();
    await page.getByRole('button', { name: 'tst' }).click();
    await page.getByTestId('cue-media-dialog-button').click();
    await expect(page.getByPlaceholder('No picture file')).toHaveValue('img/16x9/apples-display.avif');
    await expect(page.getByLabel('Sound start s into file.')).toHaveValue('1');
    await expect(page.getByLabel('Media Speed')).toHaveValue('1.2');
    await expect(page.getByLabel('Windup')).toHaveValue('0.1');
    await expect(page.getByLabel('Winddown')).toHaveValue('0.3');
    await expect(page.getByLabel('Device Play media file in web')).toHaveValue('groupwebplayer');
    await expect(page.getByLabel('Relative length')).toBeChecked();
    await expect(page.getByLabel('Fade sound after end')).toHaveValue('0.6');
    await expect(page.getByLabel('Sound fadein:')).toHaveValue('0.7');
    await expect(page.getByLabel('Cue Volume')).toHaveValue('0.8');
    await expect(page.getByLabel('Loops')).toHaveValue('8');
    await page.getByTestId('close-cue-media').click();
    await page.getByTestId('close-group').click();

    await deleteModule(page, 'testcue');
    await logout(page);
});
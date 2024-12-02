import { test, expect } from '@playwright/test';
import { sleep, login, logout, chandlerBoardTemplate, deleteModule, makeTagPoint } from './util';



/*
Create a module, make a chandler board, test very simple logic,
make sure tag output features work.
*/
test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);
    let module = "PlaywrightChandlerTestModule";
    
    await chandlerBoardTemplate(page);

    // Cue logic
    await page.getByTestId('cue-logic-button').click();

    // Add rule and edit the default example action
    await page.getByRole('button', { name: 'Add Rule' }).click();
    await page.getByRole('button', { name: 'goto =GROUP' }).click();


    // Action params editor has a cue field
    // When we go into default cue it should redirect to c2
    await page.getByLabel('cue', { exact: true }).fill('c2');
    //Dismiss popup selecter by clicking outside
    await page.getByRole('heading', { name: 'Automation Logic' }).click();

    await page.getByTestId("close-logic").click();

    // Go on default cue
    await page.getByRole('button', { name: 'Go', exact: true }).first().click();

    // Check that worked
    await expect(page.getByRole('article')).toContainText('c2');

    // make cue c3, navigate to it
    await page.getByPlaceholder('New cue name').click();
    await page.getByPlaceholder('New cue name').fill('c3');
    await page.getByRole('button', { name: 'Add Cue' }).click();
    await page.getByRole('cell', { name: 'c3' }).click();

    // Go in c3, check we're there
    await page.getByRole('row', { name: 'c3' }).getByRole('button', { name: 'Go', exact: true }).click();
    await expect(page.getByRole('article')).toContainText('c3');

    page.once('dialog', dialog => {
        console.log(`Dialog message: ${dialog.message()}`);
        dialog.dismiss().catch(() => { });
    });
    // Delete c3
    await page.getByRole('button', { name: 'Delete Current' }).click();
    // Go to c2
    await page.getByRole('button', { name: 'Go', exact: true }).first().click();
    await expect(page.getByRole('article')).toContainText('c2');

    // Also some cue text
    await page.getByTestId('cue-text-dialog-button').click();
    await page.getByTestId('cuetext').fill('cuetext');
    await page.getByTestId("close-cue-text").click();

    // Make a new cue from the alert sound    
    await page.getByTestId("cue-media-dialog-button").click();
    await page.getByRole('list').getByText('Refresh').click();

    await page.getByTestId("media-browser-container").getByText('/dev/shm/kaithem_test_env/assets/').click();

    // It must exist
    await page.getByRole('button', { name: 'New(sound)' }).first().click();
    await expect(page.locator('#cuesbox')).toContainText('alert');


    await page.getByTestId("close-cue-media").click();

    // Set the cue length to 0 so it doesn't end too soon
    await page.getByRole('cell', { name: '0.01' }).getByRole('combobox').dblclick();
    await page.getByRole('cell', { name: '0.01' }).getByRole('combobox').fill('0');
    await page.getByPlaceholder('New cue name').click();
    await page.getByRole('row', { name: 'alert' }).getByRole('button', { name: 'Go', exact: true }).click();


    //Select the group box in the sidebar that tells us what the cue is
    await expect(page.getByText('tst1alert')).toContainText('alert');
    // Channel adding tab
    await page.getByTestId("add-rm-fixtures-button").click();
    // Add raw dmx channek;
    await page.getByLabel('Universe').fill('dmx');

    // Click elsewhere to make dropdown suggestions box go
    await page.getByTestId("add-rm-fixtures-button").click();

    await page.getByLabel('Channel').fill('25');
    // Click elsewhere to make dropdown suggestions box go
    await page.getByTestId("add-rm-fixtures-button").click();

    await page.getByRole('button', { name: 'Add Channel to Cue' }).first().click();
    await expect(page.getByRole('main')).toContainText('dmx');

    await expect(page.getByRole('main')).toContainText('25');

    // Click elsewhere to make dropdown suggestions box go
    await page.getByTestId("add-rm-fixtures-button").click();

    await page.getByRole('button', { name: 'Normal View' }).click();

    await page.locator('summary').filter({ hasText: 'Channels' }).click();
    await page.locator('article').filter({ hasText: 'dmx' }).getByRole('slider').fill('130');
    await expect(page.getByRole('main')).toContainText('130.0');

    // Make a tag point
    await makeTagPoint(page, module, 'test_chandler_tag');

    // Go back to the light board and add the tag point
    // to the cue
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: module }).click();
    await page.getByRole('link', { name: 'Editor' }).click();
    await page.getByRole('button', { name: 'tst1' }).click();
    await page.getByTestId("add-rm-fixtures-button").click();
    await page.getByLabel('Tag', { exact: true }).click();
    await page.getByLabel('Tag', { exact: true }).fill('/test_chandler_tag');
    // Click elsewhere to make dropdown suggestions box go
    await page.getByTestId("add-rm-fixtures-button").click();

    await page.locator('div').filter({ hasText: /^Tag Add Channel to Cue$/ }).getByRole('button').click();
    await page.locator('summary').filter({ hasText: 'Channels' }).click();
    await page.locator('article').filter({ hasText: '/' }).getByRole('slider').fill('130');

    await page.getByRole('button', { name: 'Go', exact: true }).first().click();


    // Go back and make sure it actually worked
    await page.goto('http://localhost:8002/tagpoints')

    // Do this twice to give it time to render
    await sleep(300);
    await page.goto('http://localhost:8002/tagpoints')

    await expect(page.getByRole('row', { name: '/test_chandler_tag' })).toContainText('130');


    await page.goto('http://localhost:8002/chandler/editor/PlaywrightChandlerTestModule:board1');

    await page.getByRole('button', { name: 'tst1' }).click();
    await page.getByTestId('add-rm-fixtures-button').click();
    await page.getByText('Channels').click();

    await expect(page.getByRole('heading', { name: '/test_chandler_tag' })).toHaveCount(1);

    await page.getByRole('button', { name: '󰆴 Remove' }).click();
    await page.goto('http://localhost:8002/chandler/editor/PlaywrightChandlerTestModule:board1');
    await page.getByRole('button', { name: 'tst1' }).click();

    await expect(page.getByRole('heading', { name: '/test_chandler_tag' })).toHaveCount(0);


    await deleteModule(page, module);
    await logout(page);
});
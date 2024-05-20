import { test, expect } from '@playwright/test';
/*
Create a module, make a chandler board, test very simple logic,
make sure tag output features work.
*/
test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await page.goto('http://localhost:8002/');
    await page.getByRole('link', { name: 'Login' }).click();
    await page.getByLabel('Username:').click();
    await page.getByLabel('Username:').fill('admin');
    await page.getByLabel('Password:').click();
    await page.getByLabel('Password:').fill('test-admin-password');
    await page.getByRole('button', { name: 'Login as Registered User' }).click();
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('ChandlerTest');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: 'Chandler Board' }).click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill('board1');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'ChandlerTest' }).click();
    await page.getByRole('link', { name: 'Editor' }).click();
    await page.getByPlaceholder('New scene name').click();
    await page.getByPlaceholder('New scene name').fill('tst1');
    await page.getByTestId('add-scene-button').click();
    await page.getByRole('button', { name: 'tst1' }).click();
    // make cue
    await page.getByPlaceholder('New cue name').click();
    await page.getByPlaceholder('New cue name').fill('c2');
    await page.getByRole('button', { name: 'Add Cue' }).click();
    //select cue
    await expect(page.locator('#cuesbox')).toContainText('c2');
    await page.locator('#cuesbox').getByText('default', { exact: true }).click();

    // Cue logic
    await page.getByText('Cue Logic', { exact: true }).click();
    await page.getByRole('button', { name: 'Add Rule' }).click();

    // Making a rule that says when go to default, jump to cue c2
    await page.getByRole('button', { name: 'goto =SCENE' }).click();
    await page.getByText('Block Inspector Type').getByRole('row', { name: 'cue' }).getByRole('textbox').click();
    // Action params editor has a cue field
    await page.getByText('Block Inspector Type').getByRole('row', { name: 'cue' }).getByRole('textbox').fill('c2');
    await page.getByRole('heading', { name: 'Docs' }).click();
    await page.getByRole('button', { name: 'Go', exact: true }).first().click();
    await expect(page.getByRole('article')).toContainText('c2');
    await page.getByPlaceholder('New cue name').click();
    await page.getByPlaceholder('New cue name').fill('c3');
    await page.getByRole('button', { name: 'Add Cue' }).click();
    await page.getByRole('cell', { name: 'c3' }).click();
    await page.getByRole('row', { name: 'c3' }).getByRole('button', { name: 'Go', exact: true }).click();
    await expect(page.getByRole('article')).toContainText('c3');
    page.once('dialog', dialog => {
        console.log(`Dialog message: ${dialog.message()}`);
        dialog.dismiss().catch(() => { });
    });
    await page.getByRole('button', { name: 'Delete Current' }).click();
    await page.getByRole('button', { name: 'Go', exact: true }).first().click();
    await expect(page.getByRole('article')).toContainText('c2');
    await page.getByText('Cue Channel Values').click();
    await page.getByText('Cue Logic', { exact: true }).click();
    await page.getByText('Cue Text').click();
    await page.locator('details').filter({ hasText: 'Cue Text' }).getByRole('textbox').click();
    await page.locator('details').filter({ hasText: 'Cue Text' }).getByRole('textbox').fill('cuetext');
    await page.getByText('Cue Sound/Media').click();
    await page.getByRole('list').getByText('Refresh').click();
    await page.getByText('Builtin').click();
    await page.getByRole('button', { name: 'New' }).first().click();
    await expect(page.locator('#cuesbox')).toContainText('alert');
    // Set the cue length to 0 so it doesn't end too soon
    await page.getByRole('cell', { name: '0.01' }).getByRole('combobox').dblclick();
    await page.getByRole('cell', { name: '0.01' }).getByRole('combobox').fill('0');
    await page.getByPlaceholder('New cue name').click();
    await page.getByRole('row', { name: 'alert' }).getByRole('button', { name: 'Go', exact: true }).click();
    //Select the scene box in the sidebar that tells us what the cue is
    await expect(page.getByText('tst1alert')).toContainText('alert');
    await page.getByText('Cue Channel Values').click();
    await page.getByRole('button', { name: 'Channels' }).click();
    await page.getByLabel('Universe').click();
    await page.getByLabel('Universe').fill('1');
    await page.getByText('Universe Cancel').click();
    await page.getByText('Add Raw ChannelUniverse Cancel Channel Add Channel to CueAdd Tag PointTag Add').click();
    await page.getByLabel('Universe').click();
    await page.getByLabel('Universe Cancel').fill('dmx');
    await page.getByText('Add Raw ChannelUniverse dmxCancel Channel Add Channel to CueAdd Tag PointTag').click();
    await page.getByLabel('Channel').click();
    await page.getByLabel('Channel Cancel').fill('25');
    await page.getByText('Add Raw ChannelUniverse Channel CancelAdd Channel to CueAdd Tag PointTag Add').click();
    await page.getByRole('button', { name: 'Add Channel to Cue' }).first().click();
    await expect(page.getByRole('main')).toContainText('dmx');
    await expect(page.getByRole('main')).toContainText('25');
    await page.getByRole('button', { name: 'Normal View' }).click();
    await page.locator('article').filter({ hasText: 'dmx250.000' }).getByRole('slider').fill('130');
    await expect(page.getByRole('main')).toContainText('130.0');
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'ChandlerTest' }).click();
    await page.getByRole('link', { name: 'Tagpoint' }).click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill('test_tp');
    await page.getByLabel('Tag Point Name').click();
    await page.getByLabel('Tag Point Name').fill('test_to');
    await page.getByLabel('Default Value').click();
    await page.getByLabel('Default Value').fill('0');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'ChandlerTest' }).click();
    await page.getByRole('link', { name: 'Editor' }).click();
    await page.getByRole('button', { name: 'tst1' }).click();
    await page.getByRole('button', { name: 'Channels' }).click();
    await page.getByLabel('Tag', { exact: true }).click();
    await page.getByLabel('Tag', { exact: true }).fill('/test_to');
    await page.locator('div').filter({ hasText: /^Tag Add Channel to Cue$/ }).getByRole('button').click();
    await page.locator('article').filter({ hasText: '/test_tovalue'}).getByRole('slider').fill('130');
    await page.getByRole('button', { name: 'Go', exact: true }).first().click();
    await page.getByRole('link', { name: 'Tags' }).click();
    await expect(page.getByRole('row', { name: '/test_to' })).toContainText('130');
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'ChandlerTest' }).click();
    await page.getByRole('link', { name: 'Editor' }).click();
    await page.getByRole('button', { name: 'tst1' }).click();
    await page.getByRole('cell', { name: 'alert' }).click();
    await page.getByRole('row', { name: 'alert' }).getByRole('checkbox').uncheck();

    await page.getByRole('row', { name: 'alert' }).getByRole('button', { name: 'Go', exact: true }).click()

    await page.getByRole('link', { name: 'Tags' }).click();
    await expect(page.getByRole('row', { name: '/test_to' })).toContainText('0.0');
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'Delete' }).click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('ChandlerTest');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('button', { name: 'Logout(admin)' }).click();
});
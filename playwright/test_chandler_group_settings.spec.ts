import { test, expect } from '@playwright/test';
import { login, logout, makeModule, deleteModule, makeTagPoint } from './util';


async function fill_box(page, box, text: string) {
    /*Filling a box does't always work even if it does in the browser*/

    // Try this twice
    await box.click();
    await box.fill(text);

    // blur element by clicking outside
    await page.keyboard.press('Tab');
    // Do it twice

    await box.click();
    await box.fill(text);
    await page.keyboard.press('Tab');

}


test('test', async ({ page }) => {
    test.setTimeout(4800000);

    await login(page);

    makeModule(page, 'testchandlerproperties');

    await page.getByRole('button', { name: 'Add Resource' }).click();

    await page.getByTestId('add-chandler_board').click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill('b1');


    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'testchandlerproperties' }).click();
    await page.getByRole('link', { name: '󰏬 Editor' }).click();


    // Now on the editor
    await page.getByPlaceholder('New group name').dblclick();
    await page.getByPlaceholder('New group name').fill('ts1');
    await page.getByTestId('add-group-button').click();
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();
    await page.getByLabel('Slideshow Overlay').click();
    await page.getByLabel('Slideshow Overlay').fill('overlay');
    await page.getByLabel('MIDI Source').click();
    await page.getByLabel('MIDI Source').fill('midisrc');
    await page.getByPlaceholder('Next cue in list').click();
    await page.getByPlaceholder('Next cue in list').fill('foo');
    await page.getByRole('main').click();

    await page.getByLabel('Priority').fill('42');
    await page.getByLabel('Default Alpha').click();
    await page.getByLabel('Default Alpha').fill('0.22');
    await page.getByRole('heading', { name: 'Sound' }).click();

    // This doesn't seem to work the first time despite working in manual
    await page.getByLabel('Alpha', { exact: true }).fill('0.25');
    await page.getByRole('heading', { name: 'Sound' }).click();
    await page.getByLabel('Alpha', { exact: true }).fill('0.25');
    await page.getByRole('heading', { name: 'Sound' }).click();
    await page.getByLabel('Require Confirmation for Cue').click();
    await page.getByLabel('Sound Output').click();
    await page.getByLabel('Sound Output').fill('defaultout');
    await page.getByLabel('Crossfade for non-silent').click();
    await page.getByLabel('Crossfade for non-silent').fill('0.56');
    await page.getByLabel('MQTT Server').click();
    await page.getByLabel('MQTT Server').fill('ppp');
    await page.getByLabel('Sync Group Name').click();
    await page.getByLabel('Sync Group Name').fill('grp');
    await page.getByPlaceholder('Tagpoint').click();
    await page.getByPlaceholder('Tagpoint').fill('cmdtag');

    // Click away
    await page.getByLabel('Sync Group Name').click();


    // Check that the stuff is there
    await page.goto('http://localhost:8002/chandler/editor/testchandlerproperties:b1');
    await expect(page.getByRole('main')).toContainText('STATUS: MQTT');
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();

    await expect(page.getByLabel('Priority')).toHaveValue('42');

    await expect(page.getByLabel('Alpha', { exact: true })).toHaveValue('0.25');
    await expect(page.getByLabel('Default Alpha')).toHaveValue('0.22');
    await expect(page.getByLabel('Slideshow Overlay')).toHaveValue('overlay');
    await expect(page.getByLabel('MIDI Source')).toHaveValue('midisrc');
    await expect(page.getByPlaceholder('Tagpoint')).toHaveValue('cmdtag');
    await expect(page.getByPlaceholder('Next cue in list')).toHaveValue('foo');
    await expect(page.getByLabel('Sound Output')).toHaveValue('defaultout');
    await expect(page.getByLabel('Crossfade for non-silent')).toHaveValue('0.56');
    await expect(page.getByLabel('MQTT Server')).toHaveValue('ppp');
    await expect(page.getByLabel('Sync Group Name')).toHaveValue('grp');

    await page.getByTestId('close-group-settings').click();
    await page.getByTestId('close-group').click();


    // More settings
    await page.goto('http://localhost:8002/chandler/editor/testchandlerproperties:b1');
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();
    await page.getByTestId('group_blend_mode').selectOption('HTP');
    await expect(page.getByLabel('Alpha', { exact: true })).toHaveValue('0.25');
    await page.getByLabel('Default Alpha').click();

    await page.getByLabel('Sidebar info URL').click();
    await page.getByLabel('Sidebar info URL').fill('foourl');
    await page.getByLabel('Utility Group(No controls)').check();
    await page.getByLabel('Hide in Runtime Mode').check();


    await page.getByTestId('close-group-settings').click();
    await page.getByTestId('close-group').click();


    // More checking
    await page.goto('http://localhost:8002/chandler/editor/testchandlerproperties:b1');
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();
    await expect(page.getByLabel('Utility Group(No controls)')).toBeChecked();
    await expect(page.getByLabel('Hide in Runtime Mode')).toBeChecked();
    await expect(page.getByLabel('Sidebar info URL')).toHaveValue('foourl');

    await expect(page.getByTestId('group_blend_mode')).toHaveValue('HTP');

    // Now lets do the display tags and action buttons    
    await page.getByRole('button', { name: 'Add Button' }).click();

    await page.getByTestId('event_button_label').click();
    await page.getByTestId('event_button_label').fill('btn1');
    await page.getByTestId('event_button_event').click();
    await page.getByTestId('event_button_event').fill('evt1');

    await page.getByRole('button', { name: 'Add Tag' }).click();


    await fill_box(page, page.getByTestId('display_tag_label'), 'tg1');

    await fill_box(page,
        page.getByTestId('display_tag_width'), '5');


    await fill_box(page,
        page.getByTestId('display_tag_tag'), '=4');

    await page.getByTestId('display_tag_type').selectOption('Meter')

    // Waste some time to let it send

    await page.getByTestId('close-group-settings').click();
    
    // More time waste
    await page.getByTestId('close-group').click();
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('close-group').click();


    await page.goto('http://localhost:8002/chandler/editor/testchandlerproperties:b1');
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();
    await expect(page.getByRole('article')).toContainText('tg1');

    await expect(page.getByTestId('event_button_label')).toHaveValue('btn1');
    await expect(page.getByTestId('event_button_event')).toHaveValue('evt1');

    await expect(page.getByTestId('display_tag_label')).toHaveValue('tg1');
    await expect(page.getByTestId('display_tag_width')).toHaveValue('5');
    await expect(page.getByTestId('display_tag_tag')).toHaveValue('=4');
    await expect(page.getByTestId('display_tag_type')).toHaveValue('meter');

    await page.getByTestId('event_button_delete').click();
    await page.getByTestId('display_tag_delete').click();

    await page.getByLabel('Require Confirmation for Cue').check();

    // Click elsewhere, do other stuff, let it save

    await page.getByTestId('close-group-settings').click();
    await page.getByTestId('close-group').click();


    await page.goto('http://localhost:8002/chandler/editor/testchandlerproperties:b1');
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();

    await expect(page.getByLabel('Require Confirmation for Cue')).toBeChecked();


    // Now lets set stuff back to defaults

    await page.getByLabel('Sound Output').click();
    await page.getByLabel('Sound Output').fill('');
    await page.getByLabel('Crossfade for non-silent').click();
    await page.getByLabel('Crossfade for non-silent').click();
    await page.getByLabel('Crossfade for non-silent').dblclick();
    await page.getByLabel('Crossfade for non-silent').fill('');
    await page.getByLabel('Default Alpha').click();
    await page.getByLabel('Crossfade for non-silent').click();
    await page.getByLabel('Crossfade for non-silent').fill('0');
    await page.getByRole('heading', { name: 'Sound' }).click();
    await page.getByLabel('MQTT Server').dblclick();
    await page.getByLabel('MQTT Server').fill('');
    await page.getByLabel('Sync Group Name').dblclick();
    await page.getByLabel('Sync Group Name').fill('');
    await page.getByLabel('Slideshow Overlay').click({
        clickCount: 3
    });
    await page.getByLabel('Slideshow Overlay').fill('');
    await page.getByLabel('MIDI Source').dblclick();

    await page.getByLabel('MIDI Source').click({
        clickCount: 3
    });
    await page.getByLabel('MIDI Source').fill('');
    await page.getByPlaceholder('Tagpoint').click({
        clickCount: 3
    });
    await page.getByPlaceholder('Tagpoint').fill('');
    await page.getByPlaceholder('Next cue in list').dblclick();
    await page.getByPlaceholder('Next cue in list').fill('');
    await page.getByLabel('Utility Group(No controls)').uncheck();
    await page.getByLabel('Hide in Runtime Mode').uncheck();
    await page.getByLabel('Backtrack').uncheck();
    await page.getByLabel('Active By Default').uncheck();
    await page.getByLabel('Require Confirmation for Cue').uncheck();


    await page.getByTestId('close-group-settings').click();
    await page.getByTestId('close-group').click();

    // Check that it worked
    await page.goto('http://localhost:8002/chandler/editor/testchandlerproperties:b1');
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();

    await expect(page.getByLabel('MQTT Server')).toBeEmpty();
    await expect(page.getByLabel('Sync Group Name')).toBeEmpty();
    await expect(page.getByLabel('Slideshow Overlay')).toBeEmpty();
    await expect(page.getByLabel('MIDI Source')).toBeEmpty();
    await expect(page.getByPlaceholder('Tagpoint')).toBeEmpty();
    await expect(page.getByPlaceholder('Next cue in list')).toBeEmpty();
    await expect(page.getByLabel('Crossfade for non-silent')).toHaveValue('0');
    await expect(page.getByLabel('Sound Output')).toBeEmpty();
    await expect(page.getByLabel('Utility Group(No controls)')).not.toBeChecked();
    await expect(page.getByLabel('Hide in Runtime Mode')).not.toBeChecked();
    await expect(page.getByLabel('Require Confirmation for Cue')).not.toBeChecked();
    await expect(page.getByLabel('Active By Default')).not.toBeChecked();
    await expect(page.getByLabel('Backtrack')).not.toBeChecked();
    await expect(page.getByPlaceholder('Tagpoint')).toBeEmpty();
    await expect(page.getByPlaceholder('Next cue in list')).toBeEmpty();

    await page.getByText('Custom layout for slideshow').click();
    await page.getByTestId('slideshow_layout').click();
    await page.getByTestId('slideshow_layout').fill('LayoutPlaceholder');


    await page.getByTestId('close-group-settings').click();
    await page.getByTestId('close-group').click();


    await page.goto('http://localhost:8002/chandler/editor/testchandlerproperties:b1');
    await page.getByRole('button', { name: 'ts1' }).click();
    await page.getByTestId('group-properties-button').click();
    await page.getByText('Custom layout for slideshow').click();
    await expect(page.getByTestId('slideshow_layout')).toHaveValue('LayoutPlaceholder');

    await deleteModule(page, 'testchandlerproperties');
    await logout(page);
});
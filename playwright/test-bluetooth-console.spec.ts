// End-to-end test for the Bluetooth console plugin.
//
// `make dev-run-bluetooth-test` creates two virtual controllers (see
// scripts/virtual-bluetooth-setup.sh) and writes their addresses to
// /tmp/kaithem-bt/env.json.  The test only ever touches those virtual
// controllers: the real hci0 is never scanned, powered, or paired.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';
import type { Locator, Page } from '@playwright/test';

import { login, sleep } from './util';

const BASE_URL = 'http://localhost:8002';
// Matches the fallback label used by the console for unnamed devices.
const UNKNOWN_DEVICE = 'Unknown device';

interface BluetoothTestEnv {
  host_address: string;
  target_address: string;
  host_path: string;
  target_path: string;
  battery: number;
}

function loadEnv(): BluetoothTestEnv {
  const runtimeDir = process.env.KAITHEM_BT_RUNTIME_DIR ?? '/tmp/kaithem-bt';
  const path = join(runtimeDir, 'env.json');
  let raw: string;
  try {
    raw = readFileSync(path, 'utf8');
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(
      `Cannot read ${path}: ${reason}. Run the virtual Bluetooth setup ` +
        'first; when the tests run in Docker the runtime dir must be ' +
        'mounted into the playwright service.'
    );
  }
  return JSON.parse(raw) as BluetoothTestEnv;
}

function escapeRegex(value: string): string {
  return value.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

function deviceCard(page: Page, address: string): Locator {
  return page.locator(`[data-testid="bt-device"][data-address="${address}"]`);
}

function controllerCard(page: Page, address: string): Locator {
  return page.locator(
    `[data-testid="bt-controller"][data-address="${address}"]`
  );
}

/**
 * Drive the per-controller scan button until this plugin owns (or has fully
 * released) its discovery session.
 *
 * BlueZ keeps one discovery session per D-Bus sender, so the adapter-wide
 * `Discovering` flag can stay set while an unrelated application scans.  The
 * badge's `data-owned` attribute reflects only the console's own session.
 */
async function setScanning(host: Locator, scanning: boolean): Promise<void> {
  const badge = host.getByTestId('bt-controller-scanning');
  const expected = scanning ? 'true' : 'false';
  if ((await badge.getAttribute('data-owned')) === expected) {
    return;
  }
  await host.getByTestId('bt-scan').click();
  await expect(badge).toHaveAttribute('data-owned', expected, {
    timeout: 30_000,
  });
}

/**
 * Toggle a Lit-controlled checkbox with a single click.
 *
 * `check()`/`uncheck()` throw when a re-render restores the old value, which
 * happens while the REST call is in flight.  One click plus a retrying
 * assertion converges once the server snapshot arrives.
 */
async function setToggle(box: Locator, checked: boolean): Promise<void> {
  await expect(box).toBeEnabled({ timeout: 30_000 });
  if ((await box.isChecked()) !== checked) {
    await box.click();
  }
  if (checked) {
    await expect(box).toBeChecked();
  } else {
    await expect(box).not.toBeChecked();
  }
}

/**
 * Make a controller discoverable and pairable from the console.
 *
 * A peripheral only accepts a pairing request while its controller is
 * connectable, so the target is driven through the same button a user would
 * press.  The button also starts LE advertising when the adapter supports it.
 */
async function makeConnectable(controller: Locator): Promise<void> {
  const flag = (key: string): Locator =>
    controller.locator(`[data-testid="bt-controller-flag"][data-key="${key}"]`);
  const advertising = flag('Advertising');

  await controller.getByTestId('bt-connectable').click();
  for (const key of ['Powered', 'Discoverable', 'Pairable']) {
    await expect(flag(key)).toBeChecked({ timeout: 30_000 });
  }
  if (await advertising.isEnabled().catch(() => false)) {
    await expect(advertising).toBeChecked({ timeout: 30_000 });
  }
}

async function acceptPairingPrompt(page: Page): Promise<void> {
  const prompt = page.getByTestId('bt-prompt');
  const appeared = await prompt
    .waitFor({ state: 'visible', timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) {
    return;
  }
  await prompt.getByTestId('bt-prompt-accept').click();
  await expect(prompt).toHaveCount(0, { timeout: 20_000 });
}

/** Recover from a run that was interrupted after pairing. */
async function forgetIfPresent(page: Page, address: string): Promise<void> {
  const card = deviceCard(page, address);
  const paired = card.getByTestId('bt-status-paired');
  if (!(await paired.isVisible().catch(() => false))) {
    return;
  }
  page.once('dialog', (dialog) => void dialog.accept());
  await card.getByTestId('bt-forget').click();
  await expect(paired).toHaveCount(0, { timeout: 30_000 });
}

/**
 * Clear the reverse-direction bond that loopback pairing leaves on the
 * target controller.
 *
 * Both virtual controllers are serviced by the same bluetoothd, so pairing
 * creates a bond on the host side and on the target side.  The console only
 * forgets the host-side device, leaving the target-side bond behind; it
 * accumulates across runs and makes the target look paired to itself.
 */
async function forgetPeerPairing(
  page: Page,
  peerAddress: string
): Promise<void> {
  const card = deviceCard(page, peerAddress);
  if (!(await card.isVisible().catch(() => false))) {
    return;
  }
  const paired = card.getByTestId('bt-status-paired');
  if (!(await paired.isVisible().catch(() => false))) {
    return;
  }
  page.once('dialog', (dialog) => void dialog.accept());
  await card.getByTestId('bt-forget').click();
  // Only the bond has to go.  BlueZ recreates the device object as soon as the
  // peer's link produces traffic again, so the card may legitimately come back
  // unpaired; requiring the card to disappear makes this check racy.
  await expect(paired).toHaveCount(0, { timeout: 30_000 });
}

/**
 * Bring a device back to a connected state, tolerating the device dropping
 * on its own between actions.
 *
 * The virtual device may drop its link while the supervisor runs, so retry
 * the connect action rather than assuming the link stayed up.
 */
async function keepConnected(card: Locator): Promise<void> {
  const connected = card.getByTestId('bt-status-connected');
  for (let attempt = 0; attempt < 4; attempt++) {
    if (await connected.isVisible().catch(() => false)) {
      return;
    }
    const connect = card.getByTestId('bt-connect');
    if (await connect.isVisible().catch(() => false)) {
      await connect.click();
    }
    await connected
      .waitFor({ state: 'visible', timeout: 30_000 })
      .catch(() => {});
  }
  await expect(connected).toBeVisible({ timeout: 30_000 });
}

type NotificationTuple = [number, string, string];

/**
 * Read the server-side notification history.
 *
 * The feed replays its whole history on subscribe, so the DOM can match a
 * notification from an earlier run.  Reading the raw log lets the test
 * require a timestamp newer than a captured watermark instead of relying on
 * counts, which break once the history reaches its configured cap.
 */
async function recentNotifications(page: Page): Promise<NotificationTuple[]> {
  const response = await page.request.get(
    `${BASE_URL}/notifications/mostrecent`,
    { params: { count: '250' } }
  );
  expect(response.ok()).toBe(true);
  return (await response.json()) as NotificationTuple[];
}

async function latestNotificationTime(page: Page): Promise<number> {
  const history = await recentNotifications(page);
  return history.reduce(
    (newest, [timestamp]) => Math.max(newest, timestamp),
    0
  );
}

async function waitForNotification(
  page: Page,
  pattern: RegExp,
  since: number,
  timeout: number
): Promise<void> {
  await expect
    .poll(
      async () =>
        (await recentNotifications(page)).some(
          ([timestamp, , message]) =>
            timestamp > since && pattern.test(message ?? '')
        ),
      { timeout, message: `notification matching ${pattern}` }
    )
    .toBe(true);
}

test('pairs, alerts, auto-connects, and forgets a virtual device', async ({
  page,
}) => {
  test.setTimeout(480_000);
  page.setDefaultTimeout(60_000);

  const env = loadEnv();
  const targetAddress = env.target_address.toUpperCase();
  const hostAddress = env.host_address.toUpperCase();

  await login(page);
  await page.goto(`${BASE_URL}/bluetooth`);

  const host = controllerCard(page, env.host_address);
  await expect(host).toBeVisible({ timeout: 30_000 });
  await expect(host.getByTestId('bt-controller-address')).toHaveText(
    env.host_address
  );

  // The target has to be connectable before the host can pair with it.
  const targetController = controllerCard(page, env.target_address);
  await expect(targetController).toBeVisible({ timeout: 30_000 });
  const target = deviceCard(page, targetAddress);
  // Loopback pairing bonds both controllers, but the console only forgets the
  // host-side device.  Clear the stale reverse bond before pairing again so
  // interrupted runs self-heal instead of accumulating state.  The emulator
  // only reports advertisements when advertising or scanning starts, so retry
  // the setup when the first attempt does not produce a report.
  let discovered = false;
  for (let attempt = 0; attempt < 5 && !discovered; attempt++) {
    // Scan first: the emulator delivers an advertising report only to
    // controllers that are already scanning when advertising is enabled, and
    // enabling an already-enabled scan is a silent no-op that emits nothing.
    // "Make connectable" re-registers the advertisement, so it must run after
    // the scanner is listening for the report to reach us.
    await setScanning(host, true);
    await forgetPeerPairing(page, hostAddress);
    // A previous interrupted run may have left the target paired; forgetting
    // it removes the device, so it has to be rediscovered in this same pass.
    await forgetIfPresent(page, targetAddress);
    await expect(page.getByTestId('bt-error')).toHaveCount(0);
    await makeConnectable(targetController);
    discovered = await target
      .waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => true)
      .catch(() => false);
  }
  await expect(discovered).toBe(true);

  // BlueZ drops unpaired LE devices as soon as discovery stops, so keep
  // scanning: pairing works while the adapter is also discovering.
  await expect(target.getByTestId('bt-pair')).toBeVisible({ timeout: 20_000 });
  await target.getByTestId('bt-pair').click();
  await acceptPairingPrompt(page);

  await expect(target.getByTestId('bt-status-paired')).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByTestId('bt-error')).toHaveCount(0);

  // Pairing does not always keep the link up; connect explicitly so BlueZ
  // resolves the battery service and exports org.bluez.Battery1.
  const connected = target.getByTestId('bt-status-connected');
  await keepConnected(target);
  await expect(target.getByTestId('bt-battery')).toHaveText(`${env.battery}%`, {
    timeout: 45_000,
  });

  // Alerts must be on before the disconnect.  Auto-connect then brings the
  // device back without any further user interaction.
  const autoConnect = target.getByTestId('bt-auto-connect');
  const alerts = target.getByTestId('bt-alerts');
  await setToggle(autoConnect, true);
  await setToggle(alerts, true);
  // Let the saved configuration reach the supervisor.
  await sleep(1_500);

  const labels = new Set<string>([targetAddress]);
  const uiLabel = (await target.getByTestId('bt-device-name').textContent())
    ?.trim()
    .replaceAll(/\s+/g, ' ');
  if (uiLabel && uiLabel !== UNKNOWN_DEVICE) {
    labels.add(uiLabel);
    // Alert names replace characters like "#" with spaces, so the alert
    // never contains the raw BlueZ alias byte for byte.
    labels.add(uiLabel.replaceAll('#', ' '));
  }
  const labelPattern = [...labels]
    .map((label) => escapeRegex(label).replaceAll(' ', '\\s+'))
    .join('|');
  const alertText = (outcome: string) =>
    new RegExp(
      `Alarm Bluetooth ${escapeRegex(targetAddress)}: ` +
        `(?:${labelPattern}) disconnected ${outcome}`
    );

  // The server-side notification history is the source of truth.  Capture the
  // newest timestamp so each assertion requires a new notification rather than
  // matching one left behind by an earlier run.
  const alertsSince = await latestNotificationTime(page);

  await keepConnected(target);
  await target.getByTestId('bt-disconnect').click();
  await waitForNotification(
    page,
    alertText('is alerting'),
    alertsSince,
    45_000
  );

  await expect(connected).toBeVisible({ timeout: 45_000 });
  // A cleared error alert auto-acknowledges after ten seconds.
  await waitForNotification(
    page,
    alertText('returned to normal'),
    alertsSince,
    90_000
  );

  // With auto-connect off the device must stay disconnected across at least
  // one supervisor tick.
  await setToggle(autoConnect, false);
  await sleep(1_500);
  await keepConnected(target);
  await target.getByTestId('bt-disconnect').click();
  await expect(connected).toHaveCount(0, { timeout: 30_000 });
  await sleep(7_000);
  await expect(connected).toHaveCount(0);

  await keepConnected(target);

  page.once('dialog', (dialog) => void dialog.accept());
  await target.getByTestId('bt-forget').click();
  await expect(target.getByTestId('bt-status-paired')).toHaveCount(0, {
    timeout: 30_000,
  });

  // The device is rediscovered as an unpaired peer, ready to pair again.
  //
  // The virtual controllers only emit advertising reports when advertising or
  // scanning *starts*; they never repeat a report on their own.  The emulator
  // delivers a report to controllers that are already scanning at the moment
  // advertising is enabled, and enabling an already-enabled scan emits
  // nothing.  So keep the host scanning and let "Make connectable" cycle the
  // target's advertisement; that re-registration is what produces the report.
  // The emulator is racy, so retry the whole cycle a bounded number of times
  // instead of failing on the first attempt.
  let rediscovered = false;
  for (let attempt = 0; attempt < 5 && !rediscovered; attempt++) {
    await setScanning(host, true);
    await makeConnectable(targetController);
    rediscovered = await target
      .waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => true)
      .catch(() => false);
  }
  await expect(rediscovered).toBe(true);
  await expect(target.getByTestId('bt-pair')).toBeVisible({ timeout: 20_000 });
  await expect(target.getByTestId('bt-status-paired')).toHaveCount(0);

  // Stopping releases only this console's session; the adapter-wide flag can
  // stay set while another application scans, so assert on ownership.
  await setScanning(host, false);
});

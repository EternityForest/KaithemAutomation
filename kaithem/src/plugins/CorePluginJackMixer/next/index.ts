import { createApp } from 'vue';
import Mixer from './Mixer.vue';

// Get boardname from the last part of the URL
const boardname = globalThis.location.pathname.split('/').at(-1);

if (!boardname) {
    document.body.innerHTML = '<h1>Error: No boardname specified</h1>';
    throw new Error('boardname query parameter required');
}

// Fetch configuration from server
async function initApp() {
    try {
        const response = await fetch(`/settings/mixer/${boardname}/config`);
        if (!response.ok) {
            throw new Error(`Failed to fetch config: ${response.statusText}`);
        }
        const config = await response.json();

        const app = createApp(Mixer, {
            boardname,
            boardApiUuid: config.boardApiUuid,
            globalApiUuid: config.globalApiUuid,
            boardResource: config.boardResource,
            boardModule: config.boardModule,
        });

        app.mount('#app');
    } catch (error) {
        console.error('Failed to initialize mixer app:', error);
        document.body.innerHTML = `<h1>Error initializing mixer:</h1><pre>${error}</pre>`;
    }
}

// eslint-disable-next-line unicorn/prefer-top-level-await
initApp();

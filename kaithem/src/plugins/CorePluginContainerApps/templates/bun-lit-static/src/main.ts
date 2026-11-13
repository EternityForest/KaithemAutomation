import { LitElement, html } from 'lit';

export class MyApp extends LitElement {
  override render() {
    return html`
      <h1>Container App</h1>
      <p>
        Edit <code>src/main.ts</code>, then press <em>Build</em> in the
        Kaithem admin page to publish the change.
      </p>
    `;
  }
}

customElements.define('my-app', MyApp);

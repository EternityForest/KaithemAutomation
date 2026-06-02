// SPDX-License-Identifier: GPL-3.0-or-later

/**
 * Alert display component using Lit and YJS
 */

import { LitElement, html, css } from 'lit';
import { getDocument } from './yjs-provider.ts';

interface AlertInfo {
  name: string;
  state: string;
  priority: string;
  description: string;
  message: string;
  zone: string | null;
}

// Declare global kaithemapi
declare global {
   
  var kaithemapi: {
    subscribe: (key: string, callback: (value: unknown) => void) => void;
    unsubscribe: (key: string, callback: (value: unknown) => void) => void;
    sendValue: (key: string, value: unknown) => void;
    checkPermission: (perm: string) => Promise<{ result: boolean }>;
  } | undefined;
}

export class KaithemAlerts extends LitElement {


  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this; // Renders to the element's light DOM
  }


  static properties = {
    showAckButton: { type: Boolean, attribute: 'show-ack-button' },
    maxAlerts: { type: Number, attribute: 'max-alerts' },
    alerts: { state: true },
  };

  alerts: Map<string, AlertInfo> = new Map();
  showAckButton = false;
  maxAlerts = 10;

  private _doc: Awaited<ReturnType<typeof getDocument>> | null = null;
  private _canAck = false;

  connectedCallback() {
    super.connectedCallback();
    
    // Read attributes
    this.showAckButton = this.hasAttribute('show-ack-button');
    const maxAttribute = this.getAttribute('max-alerts');
    if (maxAttribute) {
      this.maxAlerts = Number.parseInt(maxAttribute, 10) || 10;
    }
    
    this._initAlerts();
  }

  private async _initAlerts() {
    // Check if user can acknowledge
    if (typeof kaithemapi !== 'undefined') {
      try {
        const permResult = await kaithemapi.checkPermission('acknowledge_alerts');
        this._canAck = permResult;
      } catch {
        this._canAck = false;
      }
    }

    // Get the YJS document
    this._doc = getDocument('/system/active_alerts');
    this._syncFromYjs();

    // Subscribe to updates
    if (this._doc) {
      const alertsMap = this._doc.get('alerts', this._doc.Map);
      alertsMap.observe(this._handleUpdate.bind(this));
    }

    // Also subscribe to the widget for real-time updates
    if (typeof kaithemapi !== 'undefined') {
      kaithemapi.subscribe('syncdb:/system/active_alerts', () => {
        this._syncFromYjs();
      });
    }
  }

  private _syncFromYjs() {
    if (!this._doc) return;

    try {
      // Get the shared alert map - Y.Map in JavaScript
      const alertsMap = this._doc.getMap('alerts');
      const newAlerts = new Map<string, AlertInfo>();

      // Y.Map is iterable, but we need to handle it properly
      alertsMap.forEach((value: unknown, key: string) => {
        if (value && typeof value === 'object') {
          newAlerts.set(key, value as AlertInfo);
        }
      });

      this.alerts = newAlerts;
      this.requestUpdate();
    } catch (error) {
      console.error('Failed to sync alerts from YJS:', error);
    }
  }

  private _handleUpdate() {
    this._syncFromYjs();
  }

  private async _ackAlert(alertName: string) {
    if (!this._canAck) return;

    try {
      const response = await fetch(`/api/alerts/ack/${encodeURIComponent(alertName)}`, {
        method: 'POST',
      });

      if (!response.ok) {
        console.error('Failed to acknowledge alert:', await response.text());
      }
    } catch (error) {
      console.error('Error acknowledging alert:', error);
    }
  }

  private _getPriorityClass(priority: string): string {
    switch (priority?.toLowerCase()) {
      case 'critical': {
        return 'critical';
      }
      case 'error': {
        return 'error';
      }
      case 'warning': {
        return 'warning';
      }
      default: {
        return 'info';
      }
    }
  }

  render() {
    const alertList = [...this.alerts.values()].slice(0, this.maxAlerts);

    if (alertList.length === 0) {
      return html`<div class="empty-state">No active alerts</div>`;
    }

    return html`
      ${alertList.map(
        (alert) => html`
          <div class="alert ${this._getPriorityClass(alert.priority)} margin flex-row margin padding">
            <div class="flex-col grow">
              <header>${alert.name}</header>
              <div class="alert-message">${alert.message || alert.description}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;" class="no-grow">
              <span class="alert-state">${alert.state}</span>










              ${this.showAckButton && this._canAck && alert.state === 'active'
                ? html`
                    <button
                      class="ack-button"
                      @click="${() => this._ackAlert(alert.name)}"
                    >
                      ACK
                    </button>
                  `
                : ''}
            </div>
          </div>
        `
      )}
    `;
  }
}

// Notifications are sent as tuples: [timestamp, topic, message]
type NotificationTuple = [number, string, string];

export class KaithemNotifications extends LitElement {
  static properties = {
    source: { type: String },
  };



  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this; // Renders to the element's light DOM
  }

  private _notifications: NotificationTuple[] = [];
  private _source: string = '';

  set source(value: string) {
    this._source = value;
    this._subscribe();
  }

  get source(): string {
    return this._source;
  }

  private _subscribe() {
    if (!this._source || !globalThis.kaithemapi) return;

    globalThis.kaithemapi.subscribe(this._source, (message: unknown) => {
      if (!message || !Array.isArray(message)) return;

      const [type, data] = message as [string, unknown];

      if (type === 'all') {
        this._notifications = [...(data as NotificationTuple[])].reverse();
      } else if (type === 'notification') {
        // data is [timestamp, topic, message]
        this._notifications.unshift(data as NotificationTuple);
        this._notifications = this._notifications.slice(-100);

        // Scroll to top
        setTimeout(() => {
          const element = this.shadowRoot?.querySelector('.scroll');
          if (element) element.scrollTop = 0;
        }, 250);
      }

      this.requestUpdate();
    });
  }

  render() {
    return html`
      <div class="scroll">
        ${this._notifications.map(
          (n) => {
            const topic = n[1] || '';
            return html`
              <div class="alert ${this._getClass(topic)} margin flex-row gaps">
                <small class="no-grow w-6rem">${new Date((n[0] || 0) * 1000).toLocaleString()}</small>
                <p class="grow">${n[2] || ''}</p>
              </div>
            `;
          }
        )}
      </div>
    `;
  }

  private _getClass(topic: string): string {
    if (!topic) return 'notification';
    if (topic.includes('critical')) return 'danger';
    if (topic.includes('errors')) return 'danger';
    if (topic.includes('important')) return 'highlight';
    if (topic.includes('warnings')) return 'warning';
    return 'notification';
  }
}

// Register the custom elements
customElements.define('kaithem-alerts', KaithemAlerts);
customElements.define('kaithem-notifications', KaithemNotifications);
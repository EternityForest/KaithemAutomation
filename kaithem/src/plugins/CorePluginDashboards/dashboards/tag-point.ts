/**
 * Variable component - stores and outputs a value.
 */

import { html, TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import { DashboardComponent } from "dashbeard/src/components/dashboard-component";
import type { ComponentConfig } from "dashbeard/src/boards/board-types";
import type { ComponentTypeSchema } from "dashbeard/src/editor/types";
import { doSerialized } from "dashbeard/src/core/serialized-actions";

import { Port, SourceType } from "dashbeard/src/flow/port";
import type { PortData } from "dashbeard/src/flow/data-types";

import { kaithemapi } from "/static/js/widget.mjs";

/**
 * Variable component - simple storage and output of values.
 * Used for constants, state, or user-input values.
 */
@customElement("ds-tagpoint")
export class TagpointComponent extends DashboardComponent {
  static readonly typeSchema: ComponentTypeSchema = {
    name: "tagpoint",
    displayName: "Tag Point",
    category: "data",
    description: "Connect to a KaithemAutomation tag point",
    configSchema: {
      type: "object",
      properties: {
        tag: {
          type: "string",
          description: "The name of the tag point",
          default: "",
        },

        visible: {
          type: "boolean",
          description: "Display in UI",
          default: true,
        },
      },
    },
  };

  /**
   * Reactive property for the current value.
   */
  @property({ type: Object }) value: unknown = null;

  /**
   * Display label.
   */
  @property() label: string = "Variable";


  @property() visible: boolean = true;

  public tagParams: {
    min?: number;
    max?: number;
    hi?: number;
    lo?: number;
    step?: number;
    unit?: number;
    type?: string;
    subtype?: string;
    readonly?: boolean;
  } = {};

  private prevTag = "";

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async upd(data: any) {
    this.value = data;
    this.requestUpdate();
    await this.sendData("value", this.value);
  }
  async register() {
    const tagName: string = this.componentConfig.config.tag as string;
    if (this.prevTag.length > 0) {
      kaithemapi.unsubscribe("tag:" + this.prevTag, this.boundSubscriber);
    }
    kaithemapi.subscribe("tag:" + tagName, this.boundSubscriber);

    this.prevTag = tagName;
    const url = "/tag_api/info" + tagName;

    const response = await fetch(url, {
      method: "GET",
    });

    const myArray = await response.json();

    for (const i of ["min", "max", "hi", "lo", "step", "unit"]) {
      if (myArray[i]) {
        this.tagParams[i] = myArray[i];
      }
    }

    this.tagParams.subtype = myArray.subtype ? myArray.subtype : "";
    this.tagParams.readonly = !myArray.writePermission;

    this.value = myArray.lastVal;

    let currentPort: Port | null = null;
    try {
      // Check if type changed - requires recreation with new port
      currentPort = this.node.getOutputPort("value");
    } catch {
      //Pass
    }
    let newType: string = this.tagParams.type!;
    if (this.tagParams.subtype) {
      newType = newType + "." + this.tagParams.subtype;
    }

    if (currentPort) {
      if (currentPort && currentPort.type !== newType) {
        // Type changed - request recreation
        this.requestRecreation().catch((error) => {
          console.error("Failed to recreate tag component:", error);
        });
        return; // Don't update - component will be recreated
      }
    } else {
      this.node
        .addPort(new Port("value", newType, true))
        .addDataHandler(this.onPortData.bind(this));
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async pushData(d: any) {
    if (d != this.value) {
      this.value = d;
      if (this.tagParams.subtype == "trigger") {
        kaithemapi.sendTrigger(this.prevTag, d);
      } else {
        kaithemapi.sendValue(this.prevTag, d);
      }
    }
  }

  async getData() {
    return this.value;
  }
  async close() {
    kaithemapi.unsubscribe("tag:" + this.prevTag, this.boundSubscriber);
  }

  constructor(config: ComponentConfig) {
    super(config);

    this.value = config.config.defaultValue ?? null;

    this.onConfigUpdate();
    this.register();
  }

  protected async onPortData(
    data: PortData,
    sourceType: SourceType
  ): Promise<void> {
    if (data.value === this.value) return;
    if (sourceType === SourceType.PortOwner) return;
    this.value = data.value;
    this.requestUpdate();
    await this.sendData("value", this.value);
  }

  private boundSubscriber = this.upd.bind(this);

  /**
   * Synchronize component value with node config.
   * Detects type changes and requests recreation if needed.
   */
  public override onConfigUpdate(): void {
    const config = this.componentConfig;
    if (config) {
      this.label = (config.config.label as string) || "Variable";
      this.visible = (config.config.visible as boolean);
      this.register();
    }
    this.requestUpdate();
  }

  /**
   * Input handler - when user changes the value.
   */
  private handleValueChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    let newValue: unknown = target.value;

    // Try to parse as number
    if (!isNaN(Number(newValue)) && newValue !== "") {
      newValue = Number(newValue);
    }
    this.pushData(newValue);

    this.value = newValue;
    doSerialized(() => this.sendData("value", this.value));
  }

  /**
   * Render the variable component.
   */
  override render(): TemplateResult {
    return html`
      <div class="small-dashboard-widget-container">
        <label>${this.label}</label>
        <input
          type="text"
          class="w-full${this.visible?'':' hidden'}"
          .value="${String(this.value)}"
          @change="${this.handleValueChange.bind(this)}"
          placeholder="Enter value" />
      </div>
    `;
  }
}

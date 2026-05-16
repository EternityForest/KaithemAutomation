export interface KaithemAPI {
  subscribe(key: string, callback: (value: any) => void): void;
  unsubscribe(key: string, callback: (value: any) => void): void;
  checkPermission(perm: string): Promise<any>;
}

export interface APIWidget {
  // Define API Widget interface as needed
}

export declare const kaithemapi: KaithemAPI;
export declare const APIWidget: any;

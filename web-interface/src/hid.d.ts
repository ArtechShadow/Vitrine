interface HIDDevice {
  opened: boolean;
  productName?: string;
  vendorId: number;
  productId: number;
  open(): Promise<void>;
  close(): Promise<void>;
  addEventListener(type: "inputreport", listener: (event: HIDInputReportEvent) => void): void;
  removeEventListener(type: "inputreport", listener: (event: HIDInputReportEvent) => void): void;
}

interface HIDInputReportEvent extends Event {
  readonly device: HIDDevice;
  readonly reportId: number;
  readonly data: DataView;
}

interface HIDDeviceFilter {
  vendorId?: number;
  productId?: number;
}

interface HIDConnectionEvent extends Event {
  readonly device: HIDDevice;
}

interface HID extends EventTarget {
  requestDevice(options: { filters: HIDDeviceFilter[] }): Promise<HIDDevice[]>;
  getDevices(): Promise<HIDDevice[]>;
  addEventListener(type: "connect" | "disconnect", listener: (event: HIDConnectionEvent) => void): void;
  removeEventListener(type: "connect" | "disconnect", listener: (event: HIDConnectionEvent) => void): void;
}

interface Navigator {
  readonly hid: HID;
}
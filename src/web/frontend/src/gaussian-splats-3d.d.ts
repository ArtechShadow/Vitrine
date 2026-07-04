// Minimal ambient declaration for @mkkellogg/gaussian-splats-3d.
// The package ships no bundled type definitions; we declare only the surface
// the SplatViewer component uses. Kept deliberately loose (unknown-typed
// handles) — the component narrows what it touches at runtime.

declare module "@mkkellogg/gaussian-splats-3d" {
  export interface ViewerOptions {
    rootElement?: HTMLElement;
    cameraUp?: [number, number, number];
    initialCameraPosition?: [number, number, number];
    initialCameraLookAt?: [number, number, number];
    /** We deliberately keep this false so no SharedArrayBuffer / COOP+COEP is required. */
    sharedMemoryForWorkers?: boolean;
    /** Kept false to avoid the WebGL2 compute path and stay portable on the loopback host. */
    gpuAcceleratedSort?: boolean;
    webXRMode?: unknown;
    [key: string]: unknown;
  }

  export interface AddSceneOptions {
    showLoadingUI?: boolean;
    splatAlphaRemovalThreshold?: number;
    progressiveLoad?: boolean;
    position?: [number, number, number];
    rotation?: [number, number, number, number];
    scale?: [number, number, number];
    [key: string]: unknown;
  }

  export class Viewer {
    constructor(options: ViewerOptions);
    addSplatScene(url: string, options?: AddSceneOptions): Promise<void>;
    start(): void;
    update?(): void;
    forceRenderNextFrame?(): void;
    getSceneCount?(): number;
    dispose(): unknown;
    [key: string]: unknown;
  }

  export const WebXRMode: { VR: unknown; AR: unknown };
}

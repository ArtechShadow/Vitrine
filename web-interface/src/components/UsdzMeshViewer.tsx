import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { USDZLoader } from "three/examples/jsm/loaders/USDZLoader.js";
import {
  sceneTransformToPosition,
  sceneTransformToQuaternion,
  sceneTransformToScale,
  type SceneTransform,
} from "../lib/sceneTransform";

interface Props {
  sourceUrl: string;
  title?: string;
  sourceLabel?: string;
  immersive?: boolean;
  modelScale?: [number, number, number];
  modelPosition?: [number, number, number];
  modelRotation?: [number, number, number, number];
  sceneTransform?: Partial<SceneTransform> | null;
  cameraDistanceMultiplier?: number;
  environmentLabel?: string;
  onEnvironmentChange?: () => void;
}

function applyModelTransform(
  model: THREE.Group,
  modelScale?: [number, number, number],
  modelPosition?: [number, number, number],
  modelRotation?: [number, number, number, number],
) {
  if (modelScale) model.scale.set(modelScale[0], modelScale[1], modelScale[2]);
  else model.scale.set(1, 1, 1);

  if (modelPosition) model.position.set(modelPosition[0], modelPosition[1], modelPosition[2]);
  else model.position.set(0, 0, 0);

  if (modelRotation) model.quaternion.set(modelRotation[0], modelRotation[1], modelRotation[2], modelRotation[3]);
  else model.quaternion.set(0, 0, 0, 1);
}

function frameModel(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  model: THREE.Group,
  cameraDistanceMultiplier: number,
  modelScale?: [number, number, number],
  modelPosition?: [number, number, number],
  modelRotation?: [number, number, number, number],
) {
  applyModelTransform(model, modelScale, modelPosition, modelRotation);

  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 0.001);
  const fov = camera.fov * (Math.PI / 180);
  const distance = (maxDim / (2 * Math.tan(fov / 2))) * 1.65 * cameraDistanceMultiplier;

  camera.position.set(center.x + distance * 0.42, center.y + distance * 0.18, center.z + distance);
  camera.near = Math.max(0.001, distance / 200);
  camera.far = Math.max(100, distance * 20);
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

export default function UsdzMeshViewer({
  sourceUrl,
  title,
  sourceLabel,
  immersive = false,
  modelScale,
  modelPosition,
  modelRotation,
  sceneTransform,
  cameraDistanceMultiplier = 1,
  environmentLabel,
  onEnvironmentChange,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasHostRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const frameRef = useRef(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const appliedModelScale = useMemo(
    () => (sceneTransform ? sceneTransformToScale(sceneTransform) : modelScale),
    [modelScale, sceneTransform],
  );
  const appliedModelPosition = useMemo(
    () => (sceneTransform ? sceneTransformToPosition(sceneTransform) : modelPosition),
    [modelPosition, sceneTransform],
  );
  const appliedModelRotation = useMemo(
    () => (sceneTransform ? sceneTransformToQuaternion(sceneTransform) : modelRotation),
    [modelRotation, sceneTransform],
  );

  useEffect(() => {
    const host = canvasHostRef.current;
    if (!host) return;

    let disposed = false;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x020406);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    host.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.rotateSpeed = 0.72;
    controls.zoomSpeed = 0.9;
    controls.panSpeed = 0.75;
    controlsRef.current = controls;

    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    scene.environment = pmrem.fromScene(room).texture;
    room.dispose();
    pmrem.dispose();

    scene.add(new THREE.HemisphereLight(0xffffff, 0x2a2a2a, 0.55));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.15);
    keyLight.position.set(4, 8, 6);
    scene.add(keyLight);

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (width === 0 || height === 0) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    setLoading(true);
    setLoadError(null);

    const loader = new USDZLoader();
    loader.load(
      sourceUrl,
      (group: THREE.Group) => {
        if (disposed) return;
        modelRef.current = group;
        scene.add(group);
        frameModel(camera, controls, group, cameraDistanceMultiplier, appliedModelScale, appliedModelPosition, appliedModelRotation);
        setLoading(false);
      },
      undefined,
      (error: unknown) => {
        if (disposed) return;
        console.error("USDZ load failed", error);
        setLoadError("Failed to load textured mesh - the USDZ asset may be unavailable.");
        setLoading(false);
      },
    );

    return () => {
      disposed = true;
      cancelAnimationFrame(frameRef.current);
      resizeObserver.disconnect();
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === host) {
        host.removeChild(renderer.domElement);
      }
      rendererRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
      modelRef.current = null;
    };
  }, [appliedModelPosition, appliedModelRotation, appliedModelScale, cameraDistanceMultiplier, sourceUrl]);

  useEffect(() => {
    const model = modelRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!model || !camera || !controls) return;
    frameModel(camera, controls, model, cameraDistanceMultiplier, appliedModelScale, appliedModelPosition, appliedModelRotation);
  }, [appliedModelPosition, appliedModelRotation, appliedModelScale, cameraDistanceMultiplier]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;

    const blockPageScroll = (event: WheelEvent) => {
      event.preventDefault();
    };
    wrap.addEventListener("wheel", blockPageScroll, { passive: false, capture: true });
    return () => wrap.removeEventListener("wheel", blockPageScroll, { capture: true });
  }, [sourceUrl]);

  return (
    <div
      ref={wrapRef}
      className={`preview-viewer splat-viewer-wrap ${immersive ? "splat-viewer-wrap--immersive" : ""}`}
    >
      {immersive ? (
        <button type="button" className="splat-environment-button" onClick={onEnvironmentChange}>
          Preview environment{environmentLabel ? `: ${environmentLabel}` : ""}
        </button>
      ) : (
        <div className="preview-toolbar">
          {title ? (
            <span className="preview-title">
              {title}
              {sourceLabel ? <small>{sourceLabel}</small> : null}
            </span>
          ) : (
            <span />
          )}
          <div className="preview-toolbar-actions">
            {loading && <span className="muted">Loading mesh...</span>}
          </div>
        </div>
      )}
      <div ref={canvasHostRef} className="splat-canvas-host" />
      {loadError && <p className="muted preview-error">{loadError}</p>}
      <p className="muted preview-hint">
        {immersive
          ? "Drag to orbit - scroll to zoom - change the preview environment to reframe"
          : "Drag to orbit - scroll to zoom"}
      </p>
    </div>
  );
}

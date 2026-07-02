import { useState } from "react";
import { Link } from "react-router-dom";
import UsdzMeshViewer from "../components/UsdzMeshViewer";

const KETCHUP_MESH_URL = "/models/KetchupTest_textured_mesh_medpoly.usdz";

type MeshPreviewEnvironment = {
  id: string;
  label: string;
  modelScale: [number, number, number];
  modelRotation: [number, number, number, number];
  cameraDistanceMultiplier: number;
};

function yRotation(degrees: number): [number, number, number, number] {
  const radians = (degrees * Math.PI) / 180;
  return [0, Math.sin(radians / 2), 0, Math.cos(radians / 2)];
}

const MESH_PREVIEW_ENVIRONMENTS: MeshPreviewEnvironment[] = [
  {
    id: "interior",
    label: "Close-up",
    modelScale: [1, 1, 1],
    modelRotation: yRotation(18),
    cameraDistanceMultiplier: 0.72,
  },
  {
    id: "overview",
    label: "Overview",
    modelScale: [1, 1, 1],
    modelRotation: yRotation(18),
    cameraDistanceMultiplier: 1.1,
  },
  {
    id: "survey",
    label: "Survey",
    modelScale: [1, 1, 1],
    modelRotation: yRotation(18),
    cameraDistanceMultiplier: 1.75,
  },
];

export default function ImmersiveViewer() {
  const [environmentIndex, setEnvironmentIndex] = useState(0);
  const activeEnvironment = MESH_PREVIEW_ENVIRONMENTS[environmentIndex];

  function cycleEnvironment() {
    setEnvironmentIndex((index) => (index + 1) % MESH_PREVIEW_ENVIRONMENTS.length);
  }

  return (
    <section
      className={`immersive-splat-page immersive-splat-page--${activeEnvironment.id}`}
      aria-label="Immersive textured mesh viewer"
    >
      <header className="immersive-splat-header">
        <Link to="/" className="btn-link immersive-back">
          Back
        </Link>
        <div>
          <p className="workspace-kicker">Immersive viewer</p>
          <h1>Ketchup Test textured mesh</h1>
        </div>
      </header>
      <UsdzMeshViewer
        title="Ketchup Test"
        sourceLabel="Med-poly USDZ - local sample"
        sourceUrl={KETCHUP_MESH_URL}
        immersive
        modelScale={activeEnvironment.modelScale}
        modelRotation={activeEnvironment.modelRotation}
        cameraDistanceMultiplier={activeEnvironment.cameraDistanceMultiplier}
        environmentLabel={activeEnvironment.label}
        onEnvironmentChange={cycleEnvironment}
      />
    </section>
  );
}
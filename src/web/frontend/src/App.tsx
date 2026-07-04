import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import HomePage from "./pages/HomePage";
import ArchiveLibrary from "./pages/ArchiveLibrary";
import CreateArchiveWizard from "./pages/CreateArchiveWizard";
import SceneWorkspace from "./pages/SceneWorkspace";
import Pipeline from "./pages/Pipeline";
import ImmersiveViewer from "./pages/ImmersiveViewer";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/library" element={<ArchiveLibrary />} />
        <Route path="/create" element={<CreateArchiveWizard />} />
        <Route path="/scenes/:sceneId" element={<SceneWorkspace />} />
        <Route path="/pipeline" element={<Pipeline />} />
        {/* /upload is a legacy alias from the PR; deep-link straight into the wizard. */}
        <Route path="/upload" element={<Navigate to="/create?source=video" replace />} />
      </Route>
      <Route path="/viewer" element={<ImmersiveViewer />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

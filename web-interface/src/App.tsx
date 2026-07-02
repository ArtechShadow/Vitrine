import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell";
import HomePage from "./pages/HomePage";
import ArchiveLibrary from "./pages/ArchiveLibrary";
import CreateArchiveWizard from "./pages/CreateArchiveWizard";
import SceneWorkspace from "./pages/SceneWorkspace";
import Pipeline from "./pages/Pipeline";
import ImmersiveViewer from "./pages/ImmersiveViewer";
import "./App.css";
import "./friendly-ui.css";

export default function App() {
  const location = useLocation();
  const immersiveRoute = location.pathname === "/viewer";

  return (
    <div className={`app ${immersiveRoute ? "app-immersive" : ""}`}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/library" element={<ArchiveLibrary />} />
          <Route path="/create" element={<CreateArchiveWizard />} />
          <Route path="/scenes/:sceneId" element={<SceneWorkspace />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/upload" element={<Navigate to="/create?source=video" replace />} />
        </Route>
        <Route path="/viewer" element={<ImmersiveViewer />} />
      </Routes>
    </div>
  );
}
import {
  BarChart3,
  Database,
  Gauge,
  GitBranch,
  Settings,
  UploadCloud,
} from "lucide-react";
import { NavLink, Route, Routes } from "react-router-dom";
import { AsIsExplorer } from "../features/as-is/AsIsExplorer";
import { DatasetsPage } from "../features/datasets/DatasetsPage";
import { HomePage } from "../features/home/HomePage";
import { IngestionPage } from "../features/ingestion/IngestionPage";
import { QuantumPage } from "../features/quantum-config/QuantumPage";
import { ThemeToggle } from "../shared/theme/ThemeToggle";

const nav = [
  { to: "/", label: "Home", icon: Gauge },
  { to: "/quantum", label: "Quantum", icon: Settings },
  { to: "/ingesta", label: "Ingesta", icon: UploadCloud },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/as-is", label: "As-Is", icon: GitBranch },
];

export function App() {
  return (
    <div className="app-shell">
      <aside className="side-nav" aria-label="Principal">
        <div className="brand">
          <div className="brand-lockup">
            <BarChart3 aria-hidden="true" />
            <span>SDS Quantum</span>
          </div>
          <ThemeToggle />
        </div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} end={item.to === "/"}>
                <Icon aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <main className="main-pane">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/quantum" element={<QuantumPage />} />
          <Route path="/ingesta" element={<IngestionPage />} />
          <Route path="/datasets" element={<DatasetsPage />} />
          <Route path="/as-is" element={<AsIsExplorer />} />
        </Routes>
      </main>
    </div>
  );
}

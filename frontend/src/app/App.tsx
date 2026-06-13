import {
  BarChart3,
  Database,
  Gauge,
  GitBranch,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  UploadCloud,
} from "lucide-react";
import { useState } from "react";
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
  const [isSidebarCollapsed, setSidebarCollapsed] = useState(true);
  const SidebarToggleIcon = isSidebarCollapsed ? PanelLeftOpen : PanelLeftClose;
  const sidebarToggleLabel = isSidebarCollapsed
    ? "Expandir navegación"
    : "Contraer navegación";

  return (
    <div
      className="app-shell"
      data-sidebar={isSidebarCollapsed ? "collapsed" : "expanded"}
    >
      <aside
        className="side-nav"
        aria-label="Principal"
        data-state={isSidebarCollapsed ? "collapsed" : "expanded"}
      >
        <div className="side-nav-header">
          <div className="brand-lockup" title="SDS Quantum">
            <span className="brand-mark" aria-hidden="true">
              <BarChart3 />
            </span>
            <span className="brand-name">SDS Quantum</span>
          </div>
          <div className="side-nav-controls">
            <button
              className="sidebar-toggle"
              type="button"
              aria-label={sidebarToggleLabel}
              aria-expanded={!isSidebarCollapsed}
              aria-controls="primary-navigation"
              title={sidebarToggleLabel}
              onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
            >
              <SidebarToggleIcon aria-hidden="true" size={18} />
            </button>
            <ThemeToggle />
          </div>
        </div>
        <nav id="primary-navigation" className="side-nav-list">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                aria-label={item.label}
                title={item.label}
              >
                <Icon aria-hidden="true" />
                <span className="nav-label">{item.label}</span>
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

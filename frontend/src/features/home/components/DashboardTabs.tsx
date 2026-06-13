type Tab = "summary" | "errors";

type Props = {
  active: Tab;
  onChange: (tab: Tab) => void;
};

export function DashboardTabs({ active, onChange }: Props) {
  return (
    <div className="dashboard-tabs" role="tablist" aria-label="Dashboard tabs">
      <button
        className={active === "summary" ? "active" : ""}
        role="tab"
        aria-selected={active === "summary"}
        onClick={() => onChange("summary")}
      >
        Resumen
      </button>
      <button
        className={active === "errors" ? "active" : ""}
        role="tab"
        aria-selected={active === "errors"}
        onClick={() => onChange("errors")}
      >
        Errores
      </button>
    </div>
  );
}

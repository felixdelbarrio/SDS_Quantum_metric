type DashboardTabItem = {
  tab: string;
  tab_name: string;
  tab_index: number;
};

type Props = {
  tabs: DashboardTabItem[];
  active: string;
  onChange: (tab: string) => void;
};

export function DashboardTabs({ tabs, active, onChange }: Props) {
  if (!tabs.length) return null;
  return (
    <div className="dashboard-tabs" role="tablist" aria-label="Dashboard tabs">
      {tabs.map((tab) => (
        <button
          key={`${tab.tab_index}:${tab.tab}`}
          className={active === tab.tab ? "active" : ""}
          role="tab"
          aria-selected={active === tab.tab}
          onClick={() => onChange(tab.tab)}
        >
          {tab.tab_name}
        </button>
      ))}
    </div>
  );
}

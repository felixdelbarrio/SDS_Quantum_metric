type EntityTab = {
  id: string;
  label: string;
  rows?: number;
};

type Props = {
  tabs: EntityTab[];
  active: string;
  onChange: (id: string) => void;
};

export function EntityTabs({ tabs, active, onChange }: Props) {
  return (
    <div className="entity-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={active === tab.id ? "active" : ""}
          type="button"
          role="tab"
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.rows !== undefined && <span>{tab.rows}</span>}
        </button>
      ))}
    </div>
  );
}

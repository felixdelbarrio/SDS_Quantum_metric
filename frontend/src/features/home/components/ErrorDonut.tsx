import { ErrorComparisonWidget } from "../types";

type Props = {
  widget: ErrorComparisonWidget;
};

const COLORS = ["#0f7b6c", "#2d5bff", "#b75f00", "#7c3aed", "#b42318"];

export function ErrorDonut({ widget }: Props) {
  const total = widget.series.reduce((sum, point) => sum + point.value, 0);
  let offset = 25;

  return (
    <article className="dashboard-card error-donut-card">
      <div className="section-heading">
        <div>
          <h2>{widget.title}</h2>
          <span>Total: {widget.total?.toLocaleString() ?? "-"}</span>
        </div>
      </div>

      {total > 0 ? (
        <div className="donut-layout">
          <svg viewBox="0 0 42 42" className="donut-chart" role="img">
            <circle cx="21" cy="21" r="15.915" />
            {widget.series.map((point, index) => {
              const dash = (point.value / total) * 100;
              const segment = (
                <circle
                  key={point.name}
                  cx="21"
                  cy="21"
                  r="15.915"
                  stroke={COLORS[index % COLORS.length]}
                  strokeDasharray={`${dash} ${100 - dash}`}
                  strokeDashoffset={offset}
                />
              );
              offset -= dash;
              return segment;
            })}
          </svg>
          <div className="donut-legend">
            {widget.series.slice(0, 6).map((point, index) => (
              <span key={point.name}>
                <i
                  className={`legend-swatch swatch-${index % COLORS.length}`}
                />
                {point.name}: {point.percent.toFixed(2)}%
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div className="analytics-empty compact">
          Sin sesiones con error calculables
        </div>
      )}
    </article>
  );
}

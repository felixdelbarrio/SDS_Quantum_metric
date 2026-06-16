import { ChartPayload } from "../../types";

type Props = {
  payload: ChartPayload;
};

export function QuantumChartLegend({ payload }: Props) {
  const legends = payload.legends.length
    ? payload.legends
    : payload.series.map((series) => ({ id: series.id, label: series.label }));

  return (
    <div className="quantum-chart-legend" aria-label="Leyenda">
      {legends.map((legend, index) => (
        <span key={String(legend.id ?? legend.label ?? index)}>
          <i className={`chart-swatch chart-swatch-${index % 5}`} />
          {String(legend.label ?? legend.id ?? "Serie")}
        </span>
      ))}
    </div>
  );
}

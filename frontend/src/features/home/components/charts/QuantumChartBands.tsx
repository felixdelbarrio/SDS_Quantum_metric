import { ChartBand } from "../../types";

type Props = {
  bands: ChartBand[];
  width: number;
  height: number;
  padding: { top: number; right: number; bottom: number; left: number };
};

export function QuantumChartBands({ bands, width, height, padding }: Props) {
  if (!bands.length) return null;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  return (
    <g className="quantum-chart-bands">
      {bands.map((band, index) => {
        const start = band.start_x ?? index / Math.max(1, bands.length);
        const end = band.end_x ?? Math.min(1, start + 0.08);
        return (
          <rect
            key={band.id}
            x={padding.left + start * plotWidth}
            y={padding.top}
            width={Math.max(1, (end - start) * plotWidth)}
            height={plotHeight}
          />
        );
      })}
    </g>
  );
}

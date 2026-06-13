import { CircleOff } from "lucide-react";

type Props = {
  title?: string;
  reason?: string | null;
  requiredDataset?: string | null;
};

export function EmptyAnalyticsState({
  title = "Sin datos locales suficientes",
  reason,
  requiredDataset,
}: Props) {
  return (
    <div className="analytics-empty">
      <CircleOff size={22} aria-hidden="true" />
      <strong>{title}</strong>
      {reason && <span>{reason}</span>}
      {requiredDataset && <code>{requiredDataset}</code>}
    </div>
  );
}

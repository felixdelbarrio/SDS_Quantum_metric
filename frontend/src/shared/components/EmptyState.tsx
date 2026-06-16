type Props = {
  title: string;
  detail?: string;
};

export function EmptyState({ title, detail }: Props) {
  return (
    <div className="analytics-empty compact">
      <strong>{title}</strong>
      {detail && <span>{detail}</span>}
    </div>
  );
}

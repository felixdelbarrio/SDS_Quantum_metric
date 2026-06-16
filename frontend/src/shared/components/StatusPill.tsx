type Props = {
  status?: string | null;
};

export function StatusPill({ status }: Props) {
  return (
    <span className={`status ${status === "passed" ? "ok" : ""}`}>
      {status ?? "-"}
    </span>
  );
}

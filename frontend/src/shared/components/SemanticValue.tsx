type Props = {
  children: string;
  intent?: "good" | "bad" | "neutral" | null;
};

export function SemanticValue({ children, intent = "neutral" }: Props) {
  return (
    <span className={`semantic-value semantic-value-${intent ?? "neutral"}`}>
      {children}
    </span>
  );
}

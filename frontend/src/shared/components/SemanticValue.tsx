import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  intent?: "good" | "bad" | "neutral" | null;
};

export function SemanticValue({ children, intent = "neutral" }: Props) {
  return (
    <span className={`semantic-value semantic-value-${intent ?? "neutral"}`}>
      {children}
    </span>
  );
}

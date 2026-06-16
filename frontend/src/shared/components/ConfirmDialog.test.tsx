import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("bloquea la accion destructiva hasta escribir la confirmacion exacta", () => {
    const onConfirm = vi.fn();
    const onInput = vi.fn();
    const { rerender } = render(
      <ConfirmDialog
        open
        title="Borrar dataset local"
        message="Escribe MX para borrar RAW, derivados y regresion."
        confirmLabel="Borrar"
        confirmationValue="MX"
        confirmationInput=""
        onConfirmationInput={onInput}
        onCancel={vi.fn()}
        onConfirm={onConfirm}
      />,
    );

    const button = screen.getByRole("button", { name: "Borrar" });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "MX" } });
    expect(onInput).toHaveBeenCalledWith("MX");

    rerender(
      <ConfirmDialog
        open
        title="Borrar dataset local"
        message="Escribe MX para borrar RAW, derivados y regresion."
        confirmLabel="Borrar"
        confirmationValue="MX"
        confirmationInput="MX"
        onConfirmationInput={onInput}
        onCancel={vi.fn()}
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

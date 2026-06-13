import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";
import { useAppStore } from "../shared/state/appStore";
import { ThemeProvider } from "../shared/theme/ThemeProvider";

const initialState = useAppStore.getInitialState();

describe("App shell navigation", () => {
  beforeEach(() => {
    localStorage.clear();
    useAppStore.setState(initialState, true);
  });

  afterEach(() => {
    cleanup();
  });

  it("abre con el lateral colapsado y conserva nombres accesibles", () => {
    renderApp();

    expect(
      screen.getByRole("complementary", { name: "Principal" }),
    ).toHaveAttribute("data-state", "collapsed");
    expect(
      screen.getByRole("button", { name: "Expandir navegación" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ingesta" })).toBeInTheDocument();
  });

  it("permite expandir y volver a colapsar el lateral", () => {
    renderApp();

    fireEvent.click(
      screen.getByRole("button", { name: "Expandir navegación" }),
    );

    expect(
      screen.getByRole("complementary", { name: "Principal" }),
    ).toHaveAttribute("data-state", "expanded");
    expect(
      screen.getByRole("button", { name: "Contraer navegación" }),
    ).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(
      screen.getByRole("button", { name: "Contraer navegación" }),
    );

    expect(
      screen.getByRole("complementary", { name: "Principal" }),
    ).toHaveAttribute("data-state", "collapsed");
  });
});

function renderApp() {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={["/as-is"]}>
        <App />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

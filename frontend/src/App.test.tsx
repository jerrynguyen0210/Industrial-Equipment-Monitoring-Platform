import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, ErrorBoundary } from "./App";

vi.mock("./PlatformStatus", () => ({
  PlatformStatus: () => (
    <section aria-label="Service status card">
      Backend and database are ready.
    </section>
  ),
}));

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("dashboard routing", () => {
  it("renders the overview shell with the current navigation item", () => {
    render(<App />);

    const heading = screen.getByRole("heading", { level: 1, name: "Overview" });
    expect(heading).toBeTruthy();
    expect(document.activeElement).not.toBe(heading);
    expect(
      screen
        .getByRole("link", { name: "Overview" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(screen.getByText("Backend and database are ready.")).toBeTruthy();
  });

  it("navigates to service status without reloading the document", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("link", { name: "Service status" }));

    expect(window.location.pathname).toBe("/status");
    const heading = screen.getByRole("heading", {
      level: 1,
      name: "Service status",
    });
    expect(heading).toBeTruthy();
    expect(document.activeElement).toBe(heading);
    expect(
      screen
        .getByRole("link", { name: "Service status" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("renders a useful not-found route", () => {
    window.history.replaceState(null, "", "/missing");
    render(<App />);

    expect(
      screen.getByRole("heading", { level: 1, name: "This page isn’t here." }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: /Go to overview/ })).toBeTruthy();
  });
});

describe("error boundary", () => {
  it("shows a recovery action and retries the child tree", () => {
    let shouldThrow = true;
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    function UnstableView() {
      if (shouldThrow) throw new Error("Render failed");
      return <p>Recovered dashboard</p>;
    }

    render(
      <ErrorBoundary>
        <UnstableView />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert").textContent).toContain(
      "Something went wrong.",
    );
    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByText("Recovered dashboard")).toBeTruthy();
  });
});

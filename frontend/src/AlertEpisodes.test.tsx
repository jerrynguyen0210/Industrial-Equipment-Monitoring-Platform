import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AlertEpisodes } from "./AlertEpisodes";

const fetchMock = vi.fn<typeof fetch>();

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const rule = {
  high_threshold: "30",
  recovery_threshold: "28",
  consecutive_readings: 3,
  unit: "celsius",
};

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("alert episodes", () => {
  it("renders persisted episodes and the backend alert rule", async () => {
    fetchMock.mockResolvedValue(
      response({
        rule,
        active_count: 1,
        episodes: [
          {
            id: 2,
            device_id: "device-demo-001",
            device_name: "Demo device",
            state: "active",
            opened_at: "2026-09-29T12:22:33Z",
            opening_value: "101.0",
            resolved_at: null,
            resolving_value: null,
          },
          {
            id: 1,
            device_id: "device-demo-001",
            device_name: "Demo device",
            state: "resolved",
            opened_at: "2026-09-29T11:00:00Z",
            opening_value: "45.0",
            resolved_at: "2026-09-29T11:10:00Z",
            resolving_value: "22.0",
          },
        ],
      }),
    );

    await act(async () => render(<AlertEpisodes />));

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/alerts");
    expect(screen.getByText("1 active")).toBeTruthy();
    expect(
      screen.getByText(/readings above 30 °C open an episode/),
    ).toBeTruthy();
    expect(
      screen.getByRole("article", {
        name: "ACTIVE high temperature alert for device-demo-001",
      }),
    ).toBeTruthy();
    expect(screen.getByText("101.0 °C")).toBeTruthy();
    expect(screen.getByText("22.0 °C")).toBeTruthy();
  });

  it("shows an empty state when no alerts are stored", async () => {
    fetchMock.mockResolvedValue(
      response({ rule, active_count: 0, episodes: [] }),
    );

    await act(async () => render(<AlertEpisodes />));

    expect(screen.getByText("No temperature alerts recorded.")).toBeTruthy();
  });

  it("reports a backend failure instead of sample data", async () => {
    fetchMock.mockResolvedValue(response({}, 503));

    await act(async () => render(<AlertEpisodes />));

    expect(screen.getByRole("alert").textContent).toContain(
      "Alert episodes could not be loaded",
    );
  });
});

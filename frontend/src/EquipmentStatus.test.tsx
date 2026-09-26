import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EquipmentStatus } from "./EquipmentStatus";

const fetchMock = vi.fn<typeof fetch>();

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-26T02:05:28Z"));
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("equipment dashboard", () => {
  it("shows an explicit loading state while the request is pending", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<EquipmentStatus />);

    expect(screen.getByRole("status").textContent).toContain(
      "Loading equipment status",
    );
  });

  it("shows the simulated reading for its device and unavailable for missing data", async () => {
    fetchMock.mockResolvedValue(
      response({
        devices: [
          {
            device_id: "device-demo-001",
            name: "Demo device",
            latest_reading: {
              value: 24.6,
              unit: "celsius",
              measured_at: "2026-09-26T02:04:28Z",
              clock_quality: "synchronised",
            },
          },
          {
            device_id: "device-without-data",
            name: "New device",
            latest_reading: null,
          },
        ],
      }),
    );

    await act(async () => render(<EquipmentStatus />));

    const demoCard = screen
      .getByRole("heading", { name: "Demo device" })
      .closest("article");
    const emptyCard = screen
      .getByRole("heading", { name: "New device" })
      .closest("article");
    expect(demoCard).not.toBeNull();
    expect(emptyCard).not.toBeNull();
    expect(within(demoCard!).getByText("24.6")).toBeTruthy();
    expect(within(demoCard!).getByText("celsius")).toBeTruthy();
    expect(within(demoCard!).getByText(/1 min ago/)).toBeTruthy();
    expect(within(demoCard!).getByText("Data available")).toBeTruthy();
    expect(within(emptyCard!).getByText("Unavailable")).toBeTruthy();
    expect(within(emptyCard!).getByText("No data")).toBeTruthy();
    expect(within(emptyCard!).queryByText("0")).toBeNull();
  });

  it("shows a useful empty state when no devices are registered", async () => {
    fetchMock.mockResolvedValue(response({ devices: [] }));
    await act(async () => render(<EquipmentStatus />));

    expect(screen.getByText(/No devices are registered yet/)).toBeTruthy();
  });

  it("shows an error state when the backend request fails", async () => {
    fetchMock.mockResolvedValue(response({ detail: "unavailable" }, 503));
    await act(async () => render(<EquipmentStatus />));

    expect(screen.getByRole("alert").textContent).toContain(
      "Equipment status could not be loaded",
    );
  });
});

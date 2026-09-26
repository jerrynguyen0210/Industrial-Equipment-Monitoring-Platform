import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { History } from "./History";

const fetchMock = vi.fn<typeof fetch>();

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const devices = {
  devices: [
    { device_id: "device-1", name: "Motor", latest_reading: null },
    { device_id: "device-2", name: "Pump", latest_reading: null },
  ],
};

function historyFor(url: string, withGaps = true) {
  const query = new URL(url, "http://localhost");
  const end = new Date(query.searchParams.get("to")!);
  const instant = (minutesAgo: number) =>
    new Date(end.getTime() - minutesAgo * 60_000).toISOString();
  return {
    device_id: query.pathname.includes("device-2") ? "device-2" : "device-1",
    unit: "celsius",
    range_start: query.searchParams.get("from"),
    range_end: query.searchParams.get("to"),
    truncated: false,
    points: withGaps
      ? [
          { measured_at: instant(4), value: "20", gap_before: true },
          { measured_at: instant(3), value: "21", gap_before: false },
          { measured_at: instant(2), value: "22", gap_before: true },
          { measured_at: instant(1), value: "23", gap_before: false },
        ]
      : [],
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("one-device history", () => {
  it("queries the selected device and range, labels units/timezone, and breaks lines at gaps", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      return response(url.endsWith("/v1/devices") ? devices : historyFor(url));
    });

    const view = render(<History />);
    await act(async () => {});

    expect(screen.getAllByText("Temperature (celsius)")).toHaveLength(2);
    expect(screen.getByText("Times shown in UTC.")).toBeTruthy();
    expect(view.container.querySelectorAll("polyline")).toHaveLength(2);
    expect(view.container.querySelectorAll("circle")).toHaveLength(4);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Device"), {
        target: { value: "device-2" },
      });
    });
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("/v1/devices/device-2/telemetry/history?"),
      ),
    ).toBe(true);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Time range"), {
        target: { value: "15m" },
      });
    });
    const lastUrl = new URL(
      String(fetchMock.mock.lastCall?.[0]),
      "http://localhost",
    );
    expect(
      Date.parse(lastUrl.searchParams.get("to")!) -
        Date.parse(lastUrl.searchParams.get("from")!),
    ).toBe(15 * 60_000);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Time display"), {
        target: { value: "local" },
      });
    });
    expect(screen.getByText(/Times shown in local time/)).toBeTruthy();
  });

  it("shows loading, empty history, and request errors explicitly", async () => {
    let resolveDevices!: (value: Response) => void;
    fetchMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveDevices = resolve;
      }),
    );
    fetchMock.mockImplementationOnce(async (input) =>
      response(historyFor(String(input), false)),
    );

    render(<History />);
    expect(screen.getByRole("status").textContent).toContain("Loading devices");
    await act(async () => resolveDevices(response(devices)));
    expect(
      screen.getByText("No synchronized readings in this time range."),
    ).toBeTruthy();
    cleanup();

    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(response(devices))
      .mockResolvedValueOnce(response({ detail: "unavailable" }, 503));
    render(<History />);
    await act(async () => {});
    expect(screen.getByRole("alert").textContent).toContain(
      "History could not be loaded",
    );
  });
});

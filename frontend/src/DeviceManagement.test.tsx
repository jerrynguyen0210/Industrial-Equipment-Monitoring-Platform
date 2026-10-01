import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DeviceManagement } from "./DeviceManagement";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("device management", () => {
  it("registers a device and shows persisted presence", async () => {
    fetchMock.mockImplementation(async (input, options) => {
      const url = String(input);
      if (options?.method === "POST") {
        return new Response("{}", { status: 201 });
      }
      return new Response(
        JSON.stringify(
          url.endsWith("/gateways")
            ? { gateways: [{ gateway_id: "gateway-1", name: "Lab" }] }
            : {
                devices: [
                  {
                    device_id: "esp32-pump-01",
                    name: "Pump ESP32",
                    gateway_id: "gateway-1",
                    enabled: true,
                    online: true,
                    last_seen_at: "2026-10-01T01:00:00Z",
                    latest_reading: null,
                  },
                ],
              },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });

    render(<DeviceManagement />);
    expect(await screen.findByText("Running · online")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Device name"), {
      target: { value: "New ESP32" },
    });
    fireEvent.change(screen.getByLabelText("Device ID"), {
      target: { value: "esp32-new-01" },
    });
    fireEvent.change(screen.getByLabelText("Gateway"), {
      target: { value: "gateway-1" },
    });
    fireEvent.change(screen.getByLabelText("Device password"), {
      target: { value: "long-secret-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Register device" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/devices",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            device_id: "esp32-new-01",
            gateway_id: "gateway-1",
            name: "New ESP32",
            password: "long-secret-123",
          }),
        }),
      );
    });
    expect(
      await screen.findByText(/Device and MQTT account registered/),
    ).toBeTruthy();
  });

  it("sets up MQTT for a device registered earlier", async () => {
    fetchMock.mockImplementation(async (input, options) => {
      if (options?.method === "POST")
        return new Response(null, { status: 204 });
      return new Response(
        JSON.stringify(
          String(input).endsWith("/gateways")
            ? { gateways: [{ gateway_id: "gateway-1", name: "Lab" }] }
            : {
                devices: [
                  {
                    device_id: "esp-nano",
                    name: "ESP nano",
                    gateway_id: "gateway-1",
                    enabled: true,
                    online: false,
                    last_seen_at: null,
                    latest_reading: null,
                  },
                ],
              },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });

    render(<DeviceManagement />);
    fireEvent.change(await screen.findByLabelText("Registered device"), {
      target: { value: "esp-nano" },
    });
    fireEvent.change(screen.getByLabelText("Registration password"), {
      target: { value: "long-device-password-123" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Set up MQTT account" }),
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/devices/esp-nano/mqtt",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ password: "long-device-password-123" }),
        }),
      );
    });
    expect(
      await screen.findByText("MQTT account is ready for esp-nano."),
    ).toBeTruthy();
  });

  it("removes a device after confirmation and refreshes the list", async () => {
    let removed = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockImplementation(async (input, options) => {
      if (options?.method === "DELETE") {
        removed = true;
        return new Response(null, { status: 204 });
      }
      return new Response(
        JSON.stringify(
          String(input).endsWith("/gateways")
            ? { gateways: [{ gateway_id: "gateway-1", name: "Lab" }] }
            : {
                devices: removed
                  ? []
                  : [
                      {
                        device_id: "esp32-pump-01",
                        name: "Pump ESP32",
                        gateway_id: "gateway-1",
                        enabled: true,
                        online: false,
                        last_seen_at: null,
                        latest_reading: null,
                      },
                    ],
              },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });

    render(<DeviceManagement />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Remove Pump ESP32 (esp32-pump-01)",
      }),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/devices/esp32-pump-01", {
        method: "DELETE",
      }),
    );
    expect(await screen.findByText("Pump ESP32 was removed.")).toBeTruthy();
    expect(screen.queryByText("esp32-pump-01 · gateway-1")).toBeNull();
  });

  it("keeps a device visible when saved history blocks removal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockImplementation(async (input, options) => {
      if (options?.method === "DELETE") {
        return new Response(
          JSON.stringify({ detail: { reason: "device_has_history" } }),
          {
            status: 409,
          },
        );
      }
      return new Response(
        JSON.stringify(
          String(input).endsWith("/gateways")
            ? { gateways: [{ gateway_id: "gateway-1", name: "Lab" }] }
            : {
                devices: [
                  {
                    device_id: "esp32-pump-01",
                    name: "Pump ESP32",
                    gateway_id: "gateway-1",
                    enabled: true,
                    online: false,
                    last_seen_at: null,
                    latest_reading: null,
                  },
                ],
              },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });

    render(<DeviceManagement />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Remove Pump ESP32 (esp32-pump-01)",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "This device has saved readings or alerts, so removal is blocked.",
    );
    expect(screen.getByText("esp32-pump-01 · gateway-1")).toBeTruthy();
  });
});

import { act, cleanup, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PlatformStatus } from "./PlatformStatus";

const fetchMock = vi.fn<typeof fetch>();
const readyBody = { status: "ready", database: "ok" };

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function showStatus() {
  await act(async () => {
    render(<PlatformStatus />);
  });
}

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
  vi.unstubAllEnvs();
});

describe("platform readiness", () => {
  it("uses the configured API prefix without trailing slashes", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://monitor.example/api///");
    vi.resetModules();
    const { getReadiness } = await import("./api");
    fetchMock.mockResolvedValue(response(readyBody));

    await getReadiness(new AbortController().signal);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://monitor.example/api/health/ready",
      {
        signal: expect.any(AbortSignal),
        cache: "no-store",
      },
    );
  });

  it("shows loading while the backend request is pending", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<PlatformStatus />);

    expect(screen.getByRole("status").textContent).toContain(
      "Checking backend and database",
    );
    expect(fetchMock).toHaveBeenCalledWith("/api/health/ready", {
      signal: expect.any(AbortSignal),
      cache: "no-store",
    });
  });

  it("shows ready when HTTP and the database readiness contract succeed", async () => {
    fetchMock.mockResolvedValue(response(readyBody));
    await showStatus();

    expect(screen.getByRole("status").textContent).toBe(
      "Backend and database are ready.",
    );
  });

  it.each([
    [
      "database outage",
      503,
      { status: "unavailable", database: "unavailable" },
    ],
    ["failed HTTP status with a ready body", 503, readyBody],
    ["missing database state", 200, { status: "ready" }],
    ["unavailable database", 200, { status: "ready", database: "unavailable" }],
    ["unavailable backend", 200, { status: "unavailable", database: "ok" }],
    ["null JSON", 200, null],
  ])("shows unavailable for %s", async (_label, status, body) => {
    fetchMock.mockResolvedValue(response(body, status));
    await showStatus();

    expect(screen.getByRole("status").textContent).toContain(
      "Backend or database is unavailable. Retrying automatically",
    );
  });

  it("shows unavailable when the proxy returns a non-JSON response", async () => {
    fetchMock.mockResolvedValue(new Response("Bad Gateway", { status: 502 }));
    await showStatus();

    expect(screen.getByRole("status").textContent).toContain("is unavailable");
  });

  it("recovers from a network failure on the next poll", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Network unavailable"))
      .mockResolvedValueOnce(response(readyBody));
    await showStatus();
    expect(screen.getByRole("status").textContent).toContain("is unavailable");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4999);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status").textContent).toBe(
      "Backend and database are ready.",
    );
  });

  it("aborts a slow request before retrying without overlapping requests", async () => {
    fetchMock
      .mockImplementationOnce(
        (_input, options) =>
          new Promise((_resolve, reject) => {
            options?.signal?.addEventListener("abort", () => {
              reject(new DOMException("Request aborted", "AbortError"));
            });
          }),
      )
      .mockResolvedValueOnce(response(readyBody));
    await showStatus();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status").textContent).toContain("Checking");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("is unavailable");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status").textContent).toContain("are ready");
  });

  it("cancels scheduled polling when unmounted", async () => {
    fetchMock.mockResolvedValue(response(readyBody));
    await showStatus();
    cleanup();

    await vi.advanceTimersByTimeAsync(15000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("aborts an in-flight request and ignores its late completion after unmount", async () => {
    let resolveRequest!: (value: Response) => void;
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve;
      }),
    );
    await showStatus();
    cleanup();

    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    await act(async () => {
      resolveRequest(response(readyBody));
    });
    await vi.advanceTimersByTimeAsync(15000);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps one polling loop after StrictMode restarts the effect", async () => {
    fetchMock.mockImplementation(async () => response(readyBody));
    await act(async () => {
      render(
        <StrictMode>
          <PlatformStatus />
        </StrictMode>,
      );
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("status").textContent).toContain("are ready");
  });
});

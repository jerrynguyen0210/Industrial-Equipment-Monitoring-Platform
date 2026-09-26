import {
  Component,
  Fragment,
  useEffect,
  useRef,
  useSyncExternalStore,
  type MouseEvent,
  type ReactNode,
} from "react";
import { PlatformStatus } from "./PlatformStatus";
import { EquipmentStatus } from "./EquipmentStatus";
import { History } from "./History";

const navigationEvent = "iemp:navigate";

function subscribeToPath(listener: () => void) {
  window.addEventListener("popstate", listener);
  window.addEventListener(navigationEvent, listener);
  return () => {
    window.removeEventListener("popstate", listener);
    window.removeEventListener(navigationEvent, listener);
  };
}

function getPathname() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

function handleInternalLink(event: MouseEvent<HTMLAnchorElement>) {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey ||
    event.currentTarget.target
  ) {
    return;
  }

  const destination = new URL(event.currentTarget.href);
  if (destination.origin !== window.location.origin) return;

  event.preventDefault();
  window.history.pushState(null, "", destination);
  window.dispatchEvent(new Event(navigationEvent));
}

function InternalLink({
  to,
  children,
  className,
  current = false,
}: {
  to: string;
  children: ReactNode;
  className?: string;
  current?: boolean;
}) {
  return (
    <a
      href={to}
      className={className}
      aria-current={current ? "page" : undefined}
      onClick={handleInternalLink}
    >
      {children}
    </a>
  );
}

function Overview() {
  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">Platform workspace</p>
        <h1 id="page-title" tabIndex={-1}>
          Overview
        </h1>
        <p className="page-description">
          Current recorded temperature readings and their measurement times.
        </p>
      </div>

      <div className="dashboard-grid">
        <div className="panel status-panel">
          <EquipmentStatus />
        </div>
        <section className="panel status-panel" aria-label="Service status">
          <PlatformStatus />
          <InternalLink to="/status" className="text-link">
            View service details <span aria-hidden="true">→</span>
          </InternalLink>
        </section>
      </div>
    </>
  );
}

function ServiceStatus() {
  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">Platform diagnostics</p>
        <h1 id="page-title" tabIndex={-1}>
          Service status
        </h1>
        <p className="page-description">
          A live readiness check for the backend and its database connection.
        </p>
      </div>
      <div className="status-content">
        <div className="panel status-panel">
          <PlatformStatus />
        </div>
        <section className="panel help-panel" aria-labelledby="check-heading">
          <h2 id="check-heading">About this check</h2>
          <p>
            The dashboard checks readiness every few seconds. If the backend or
            database is unavailable, it retries automatically.
          </p>
        </section>
      </div>
    </>
  );
}

function HistoryPage() {
  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">Equipment monitoring</p>
        <h1 id="page-title" tabIndex={-1}>
          History
        </h1>
        <p className="page-description">
          Explore recent temperature measurements for one device.
        </p>
      </div>
      <History />
    </>
  );
}

function NotFound() {
  return (
    <div className="not-found">
      <p className="eyebrow">404 · Page not found</p>
      <h1 id="page-title" tabIndex={-1}>
        This page isn’t here.
      </h1>
      <p>The address may be incorrect, or the page may have moved.</p>
      <InternalLink to="/" className="primary-link">
        Go to overview <span aria-hidden="true">→</span>
      </InternalLink>
    </div>
  );
}

export function App() {
  const path = useSyncExternalStore(subscribeToPath, getPathname, () => "/");
  const pageName =
    path === "/"
      ? "Overview"
      : path === "/history"
        ? "History"
        : path === "/status"
          ? "Service status"
          : "Page not found";
  const previousPath = useRef(path);

  useEffect(() => {
    document.title = `${pageName} | Industrial Equipment Monitoring Platform`;
    if (previousPath.current !== path) {
      document.getElementById("page-title")?.focus();
      previousPath.current = path;
    }
  }, [pageName, path]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <InternalLink to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            IE
          </span>
          <span className="brand-name">
            <strong>Industrial Equipment</strong>
            <span>Monitoring Platform</span>
          </span>
        </InternalLink>
        <nav aria-label="Main navigation" className="side-nav">
          <p className="nav-label">Workspace</p>
          <InternalLink to="/" className="nav-link" current={path === "/"}>
            <span className="nav-icon" aria-hidden="true">
              ▦
            </span>
            Overview
          </InternalLink>
          <InternalLink
            to="/history"
            className="nav-link"
            current={path === "/history"}
          >
            <span className="nav-icon" aria-hidden="true">
              ◱
            </span>
            History
          </InternalLink>
          <InternalLink
            to="/status"
            className="nav-link"
            current={path === "/status"}
          >
            <span className="nav-icon" aria-hidden="true">
              ◉
            </span>
            Service status
          </InternalLink>
        </nav>
        <p className="sidebar-footnote">Local development workspace</p>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb" aria-label="Current page">
            <span>Workspace</span>
            <span aria-hidden="true">/</span>
            <strong>{pageName}</strong>
          </div>
          <span className="environment-badge">Local environment</span>
        </header>
        <main id="main-content" className="content">
          {path === "/" ? (
            <Overview />
          ) : path === "/history" ? (
            <HistoryPage />
          ) : path === "/status" ? (
            <ServiceStatus />
          ) : (
            <NotFound />
          )}
        </main>
      </div>
    </div>
  );
}

type ErrorBoundaryState = { failed: boolean; retryKey: number };

export class ErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { failed: false, retryKey: 0 };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  private retry = () => {
    this.setState((state) => ({ failed: false, retryKey: state.retryKey + 1 }));
  };

  render() {
    if (this.state.failed) {
      return (
        <main className="error-screen">
          <div className="error-card" role="alert">
            <p className="eyebrow">Dashboard error</p>
            <h1>Something went wrong.</h1>
            <p>The dashboard could not render this view. Please try again.</p>
            <button type="button" onClick={this.retry}>
              Try again
            </button>
          </div>
        </main>
      );
    }

    return <Fragment key={this.state.retryKey}>{this.props.children}</Fragment>;
  }
}

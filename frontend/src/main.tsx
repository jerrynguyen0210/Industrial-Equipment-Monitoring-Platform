import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PlatformStatus } from "./PlatformStatus";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PlatformStatus />
  </StrictMode>,
);

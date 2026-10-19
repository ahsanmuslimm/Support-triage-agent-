import { mountWidget } from "./ChatWidget";
import { readConfig } from "./api";
import "./style.css";

function bootstrap() {
  const host = document.createElement("div");
  host.id = "triage-widget-root";
  document.body.appendChild(host);
  mountWidget(host, readConfig());
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}

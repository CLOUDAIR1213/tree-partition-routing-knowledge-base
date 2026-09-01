import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ChatSessionProvider } from "../../features/chat/ChatSessionContext";
import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

function ShellContent() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!sidebarOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSidebarOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sidebarOpen]);

  return (
    <div className="app-shell">
      <AppSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="app-main-column">
        <TopBar onOpenMenu={() => setSidebarOpen(true)} />
        <main className="route-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function AppShell() {
  return (
    <ChatSessionProvider>
      <ShellContent />
    </ChatSessionProvider>
  );
}

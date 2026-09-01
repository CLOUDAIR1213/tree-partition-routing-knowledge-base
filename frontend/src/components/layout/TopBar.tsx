import { Menu, Upload } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

export function TopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const location = useLocation();
  const isChatPage = location.pathname === "/";

  return (
    <header className="top-bar">
      <button
        aria-label="打开会话导航"
        className="icon-button mobile-menu-button"
        onClick={onOpenMenu}
        type="button"
      >
        <Menu aria-hidden="true" size={20} />
      </button>
      <div className="top-bar-spacer" />
      {isChatPage && (
        <Link
          aria-label="上传知识"
          className="primary-button upload-link"
          to="/knowledge/upload"
        >
          <span className="upload-link-icon" aria-hidden="true">
            <Upload size={16} strokeWidth={1.9} />
          </span>
          <span className="upload-link-label">上传知识</span>
        </Link>
      )}
    </header>
  );
}

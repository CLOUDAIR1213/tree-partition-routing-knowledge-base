import { BookOpenText, CirclePlus, Database, Ellipsis, Trash2, UserRound, X } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useChatSession } from "../../features/chat/ChatSessionContext";

interface AppSidebarProps {
  open: boolean;
  onClose: () => void;
}

type PendingHistoryAction =
  | { kind: "delete"; conversationId: string; title: string }
  | { kind: "clear" };

export function AppSidebar({ open, onClose }: AppSidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    conversations,
    activeConversation,
    newConversation,
    selectConversation,
    deleteConversation,
    clearConversations,
  } = useChatSession();
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] =
    useState<PendingHistoryAction | null>(null);
  const recent = conversations.filter((conversation) => conversation.messages.length);

  function startConversation() {
    newConversation();
    navigate("/");
    onClose();
  }

  function confirmHistoryAction() {
    if (!pendingAction) return;
    if (pendingAction.kind === "delete") {
      deleteConversation(pendingAction.conversationId);
    } else {
      clearConversations();
    }
    setOpenMenuId(null);
    setPendingAction(null);
    navigate("/");
  }

  return (
    <>
      <button
        aria-label="关闭会话导航"
        className="sidebar-backdrop"
        data-open={open}
        onClick={onClose}
        type="button"
      />
      <aside className="app-sidebar" data-open={open} aria-label="会话导航">
        <div className="sidebar-brand-row">
          <button
            aria-label="返回问答首页"
            className="sidebar-brand"
            onClick={() => {
              navigate("/");
              onClose();
            }}
            type="button"
          >
            <span className="brand-mark">
              <Database aria-hidden="true" size={19} strokeWidth={2} />
            </span>
            <span>分区知识库</span>
          </button>
          <button
            aria-label="关闭侧栏"
            className="icon-button sidebar-close"
            onClick={onClose}
            type="button"
          >
            <X aria-hidden="true" size={18} />
          </button>
        </div>

        <button className="new-chat-button" onClick={startConversation} type="button">
          <CirclePlus aria-hidden="true" size={17} strokeWidth={1.8} />
          <span>开启新对话</span>
        </button>

        <section className="recent-section" aria-labelledby="recent-title">
          <div className="recent-heading-row">
            <h2 id="recent-title">最近会话</h2>
            {(recent.length > 0 || conversations.length > 1) && (
              <button
                aria-label="清空全部会话"
                className="clear-conversations-button"
                onClick={() => {
                  setOpenMenuId(null);
                  setPendingAction({ kind: "clear" });
                }}
                title="清空全部会话"
                type="button"
              >
                <Trash2 aria-hidden="true" size={14} />
              </button>
            )}
          </div>
          {recent.length ? (
            <ul className="conversation-list">
              {recent.map((conversation) => (
                <li
                  className="conversation-item"
                  data-active={activeConversation.id === conversation.id}
                  key={conversation.id}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setOpenMenuId(null);
                  }}
                >
                  <div className="conversation-row">
                    <button
                      aria-current={
                        activeConversation.id === conversation.id ? "page" : undefined
                      }
                      className="conversation-select-button"
                      onClick={() => {
                        setOpenMenuId(null);
                        selectConversation(conversation.id);
                        navigate("/");
                        onClose();
                      }}
                      title={conversation.title}
                      type="button"
                    >
                      {conversation.title}
                    </button>
                    <button
                      aria-expanded={openMenuId === conversation.id}
                      aria-haspopup="menu"
                      aria-label={`更多操作：${conversation.title}`}
                      className="conversation-more-button"
                      onClick={() =>
                        setOpenMenuId((current) =>
                          current === conversation.id ? null : conversation.id,
                        )
                      }
                      title="更多操作"
                      type="button"
                    >
                      <Ellipsis aria-hidden="true" size={16} />
                    </button>
                  </div>
                  {openMenuId === conversation.id && (
                    <div
                      aria-label={`${conversation.title}的操作`}
                      className="conversation-menu"
                      role="menu"
                    >
                      <button
                        onClick={() => {
                          setOpenMenuId(null);
                          setPendingAction({
                            kind: "delete",
                            conversationId: conversation.id,
                            title: conversation.title,
                          });
                        }}
                        role="menuitem"
                        type="button"
                      >
                        <Trash2 aria-hidden="true" size={15} />
                        <span>删除会话</span>
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="conversation-empty">提问后，会话将显示在这里</p>
          )}
        </section>

        <button
          aria-current={location.pathname.startsWith("/knowledge") ? "page" : undefined}
          className="knowledge-nav-button"
          onClick={() => {
            navigate("/knowledge");
            onClose();
          }}
          type="button"
        >
          <BookOpenText aria-hidden="true" size={17} strokeWidth={1.8} />
          <span>知识库</span>
        </button>

        <div className="sidebar-user">
          <span className="user-avatar">
            <UserRound aria-hidden="true" size={16} />
          </span>
          <span>
            <strong>演示用户</strong>
            <small>本地会话</small>
          </span>
        </div>
      </aside>

      {pendingAction && (
        <div className="dialog-backdrop" role="presentation">
          <div
            aria-labelledby="history-dialog-title"
            aria-modal="true"
            className="confirm-dialog history-confirm-dialog"
            onKeyDown={(event) => {
              if (event.key === "Escape") setPendingAction(null);
            }}
            role="dialog"
          >
            <h2 id="history-dialog-title">
              {pendingAction.kind === "clear" ? "清空全部会话？" : "删除这个会话？"}
            </h2>
            <p>
              {pendingAction.kind === "clear"
                ? "全部本地历史将从此浏览器中删除，刷新页面后也不会恢复。"
                : `“${pendingAction.title}”将从此浏览器中删除，刷新页面后也不会恢复。`}
            </p>
            <div className="dialog-actions">
              <button
                autoFocus
                className="secondary-button"
                onClick={() => setPendingAction(null)}
                type="button"
              >
                取消
              </button>
              <button
                className="reject-confirm-button"
                onClick={confirmHistoryAction}
                type="button"
              >
                {pendingAction.kind === "clear" ? "确认清空" : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

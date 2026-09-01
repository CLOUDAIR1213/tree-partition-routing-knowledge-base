import { CirclePlus, Database, UserRound, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useChatSession } from "../../features/chat/ChatSessionContext";

interface AppSidebarProps {
  open: boolean;
  onClose: () => void;
}

export function AppSidebar({ open, onClose }: AppSidebarProps) {
  const navigate = useNavigate();
  const {
    conversations,
    activeConversation,
    newConversation,
    selectConversation,
  } = useChatSession();
  const recent = conversations.filter((conversation) => conversation.messages.length);

  function startConversation() {
    newConversation();
    navigate("/");
    onClose();
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
          <h2 id="recent-title">最近会话</h2>
          {recent.length ? (
            <ul className="conversation-list">
              {recent.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    aria-current={
                      activeConversation.id === conversation.id ? "page" : undefined
                    }
                    onClick={() => {
                      selectConversation(conversation.id);
                      navigate("/");
                      onClose();
                    }}
                    title={conversation.title}
                    type="button"
                  >
                    {conversation.title}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="conversation-empty">提问后，会话将显示在这里</p>
          )}
        </section>

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
    </>
  );
}

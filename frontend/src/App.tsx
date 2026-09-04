import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ChatPage } from "./pages/ChatPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { UploadPage } from "./pages/UploadPage";
import { ReviewPage } from "./pages/ReviewPage";
import { KnowledgeLibraryPage } from "./pages/KnowledgeLibraryPage";

function LegacyReviewRedirect() {
  const { documentId } = useParams();
  return <Navigate replace to={`/knowledge/documents/${documentId ?? ""}`} />;
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ChatPage />} />
        <Route path="knowledge" element={<KnowledgeLibraryPage />} />
        <Route path="knowledge/upload" element={<UploadPage />} />
        <Route path="knowledge/documents/:documentId" element={<ReviewPage />} />
        <Route path="knowledge/review/:documentId" element={<LegacyReviewRedirect />} />
        <Route path="404" element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Route>
    </Routes>
  );
}

import { createBrowserRouter, Navigate } from "react-router-dom";
import { KnowledgeUploadPage } from "@/pages/knowledge-upload";
import { KnowledgeFileTreePage } from "@/pages/knowledge-file-tree";
import { RetrievePage } from "@/pages/retrieve";

export const router = createBrowserRouter([
  { path: "/", element: <KnowledgeUploadPage /> },
  { path: "/knowledge-bases", element: <KnowledgeFileTreePage /> },
  { path: "/retrieve", element: <RetrievePage /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);

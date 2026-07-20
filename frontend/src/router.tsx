import { createBrowserRouter, Navigate } from "react-router-dom";
import { KnowledgeUploadPage } from "@/pages/knowledge-upload";

export const router = createBrowserRouter([
  { path: "/", element: <KnowledgeUploadPage /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);

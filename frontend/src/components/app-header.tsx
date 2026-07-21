import { Link, useLocation } from "react-router-dom";

interface NavLink {
  to: string;
  label: string;
}

// 每个路由下、右侧要展示的"其他页面"入口
const NAV_BY_PATH: Record<string, NavLink[]> = {
  "/": [
    { to: "/knowledge-bases", label: "知识库列表" },
    { to: "/retrieve", label: "检索调试" },
  ],
  "/knowledge-bases": [
    { to: "/", label: "知识库上传" },
    { to: "/retrieve", label: "检索调试" },
  ],
  "/retrieve": [
    { to: "/", label: "知识库上传" },
    { to: "/knowledge-bases", label: "知识库列表" },
  ],
};

export function AppHeader() {
  const { pathname } = useLocation();
  const links = NAV_BY_PATH[pathname] ?? NAV_BY_PATH["/"];

  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-3">
      <Link to="/" className="text-lg font-bold tracking-tight">
        RAG 知识文件管理
      </Link>
      <nav className="flex items-center gap-4 text-sm">
        {links.map((l) => (
          <Link key={l.to} to={l.to} className="text-muted-foreground hover:text-foreground">
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

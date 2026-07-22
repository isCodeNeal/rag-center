import { Badge } from "@/components/ui/badge";
import type { TenantPlan } from "@/types/api";

// 套餐档位 → 文案与颜色：free 灰 / standard 蓝 / pro 紫。
const PLAN_META: Record<TenantPlan, { label: string; className: string }> = {
  free: { label: "免费", className: "bg-muted text-muted-foreground" },
  standard: { label: "标准", className: "bg-blue-500 text-white hover:bg-blue-500/90" },
  pro: { label: "专业", className: "bg-purple-600 text-white hover:bg-purple-600/90" },
};

export function PlanBadge({ plan }: { plan: TenantPlan }) {
  const meta = PLAN_META[plan] ?? PLAN_META.free;
  return <Badge className={meta.className}>{meta.label}</Badge>;
}

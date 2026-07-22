import { Badge } from "@/components/ui/badge";
import { DocumentStatus } from "@/types/api";

// 文档索引状态 → 颜色与文案：1 绿色成功 / 2 红色失败 / 3 蓝色索引中。
export function StatusBadge({ status }: { status: number }) {
  switch (status) {
    case DocumentStatus.SUCCESS:
      return <Badge variant="success">成功</Badge>;
    case DocumentStatus.FAILED:
      return <Badge variant="destructive">失败</Badge>;
    case DocumentStatus.PROCESSING:
      return (
        <Badge className="bg-blue-500 text-white hover:bg-blue-500/90">索引中</Badge>
      );
    default:
      return <Badge variant="outline">未知</Badge>;
  }
}

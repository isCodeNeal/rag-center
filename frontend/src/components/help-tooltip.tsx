interface Props {
  text: string;
}

// 纯 CSS hover 提示，避免引入额外 UI 依赖。悬停问号图标显示说明。
export function HelpTooltip({ text }: Props) {
  return (
    <span className="group relative inline-flex">
      <span className="flex h-4 w-4 cursor-help items-center justify-center rounded-full border text-[10px] text-muted-foreground">
        ?
      </span>
      <span className="pointer-events-none absolute left-5 top-1/2 z-10 hidden -translate-y-1/2 whitespace-normal rounded-md border bg-popover px-2 py-1 text-xs text-popover-foreground shadow group-hover:block w-60">
        {text}
      </span>
    </span>
  );
}

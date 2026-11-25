import { Toaster as Sonner, ToasterProps } from "sonner"
import { useTheme } from "next-themes"

const Toaster = ({ ...props }: ToasterProps) => {
  // 跟随应用内选择的主题（next-themes 已把 system 解析成实际值）
  const { resolvedTheme } = useTheme()

  return (
    <Sonner
      theme={(resolvedTheme ?? 'light') as ToasterProps["theme"]}
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }

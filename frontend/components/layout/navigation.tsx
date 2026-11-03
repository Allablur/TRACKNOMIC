"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AudioLines,
  LayoutDashboard,
  Users,
  GitCompareArrows,
  Disc3,
  ChartNoAxesCombined,
  FileChartColumn,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
const links = [
  ["/dashboard", "Overview", LayoutDashboard],
  ["/artists", "Artists", Users],
  ["/compare", "Compare", GitCompareArrows],
  ["/albums", "Albums", Disc3],
  ["/genres", "Genres", ChartNoAxesCombined],
  ["/reports", "Reports", FileChartColumn],
  ["/settings", "Settings", Settings],
] as const;
export function Navigation() {
  const path = usePathname();
  return (
    <aside className="border-b border-border bg-white p-5 lg:fixed lg:inset-y-0 lg:w-60 lg:border-r">
      <Link
        href="/dashboard"
        className="mb-7 flex items-center gap-3 text-xl font-bold"
      >
        <AudioLines className="text-primary" aria-hidden="true" />
        Trackonomics
      </Link>
      <nav
        aria-label="Main navigation"
        className="flex flex-wrap gap-1 lg:flex-col"
      >
        {links.map(([href, label, Icon]) => (
          <Link
            href={href}
            key={href}
            aria-current={path.startsWith(href) ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium hover:bg-muted",
              path.startsWith(href) &&
                "bg-primary text-white hover:bg-primary/90",
            )}
          >
            <Icon size={18} aria-hidden="true" />
            {label}
          </Link>
        ))}
      </nav>
      <p className="mt-10 text-xs leading-5 text-muted-foreground">
        Catalogue intelligence.
        <br />
        Every source matters.
      </p>
    </aside>
  );
}

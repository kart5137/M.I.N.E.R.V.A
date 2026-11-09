import {
  Activity,
  BarChart3,
  BookOpen,
  Flag,
  Globe2,
  LayoutDashboard,
  type LucideIcon,
  Radar,
  TrendingUp,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Milestone that ships the page; `null` means it is available now. */
  plannedFor: string | null;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/", icon: LayoutDashboard, plannedFor: null },
  { label: "Global Surveillance", href: "/surveillance", icon: Globe2, plannedFor: null },
  { label: "Countries", href: "/countries", icon: Flag, plannedFor: null },
  { label: "Hotspots & Anomalies", href: "/hotspots", icon: Radar, plannedFor: "M6" },
  { label: "Prediction Center", href: "/predictions", icon: TrendingUp, plannedFor: null },
  { label: "Analytics", href: "/analytics", icon: BarChart3, plannedFor: null },
  { label: "Reports & Alerts", href: "/reports", icon: Activity, plannedFor: "M7" },
  { label: "About the Data", href: "/about", icon: BookOpen, plannedFor: "M7" },
];

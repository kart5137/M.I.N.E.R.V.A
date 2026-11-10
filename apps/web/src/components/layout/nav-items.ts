import {
  BarChart3,
  BellRing,
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
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Global Surveillance", href: "/surveillance", icon: Globe2 },
  { label: "Countries", href: "/countries", icon: Flag },
  { label: "Hotspots & Anomalies", href: "/hotspots", icon: Radar },
  { label: "Prediction Center", href: "/predictions", icon: TrendingUp },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Reports & Alerts", href: "/reports", icon: BellRing },
  { label: "About the Data", href: "/about", icon: BookOpen },
];

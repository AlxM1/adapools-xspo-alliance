"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Video,
  Mic,
  User,
  Share2,
  Settings,
  History,
  PlusCircle,
  Shield,
  BarChart3,
  Rss,
  Image,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "New Pipeline", href: "/pipeline/new", icon: PlusCircle },
  { name: "History", href: "/pipeline", icon: History },
  { name: "Videos", href: "/videos", icon: Video },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Sources", href: "/sources", icon: Rss },
  { name: "Thumbnails", href: "/thumbnails", icon: Image },
  { name: "Voices", href: "/voices", icon: Mic },
  { name: "Avatars", href: "/avatars", icon: User },
  { name: "Connections", href: "/connections", icon: Share2 },
  { name: "Settings", href: "/settings", icon: Settings },
];

const adminNavigation = [
  { name: "Admin Panel", href: "/admin", icon: Shield },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuthStore();

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  return (
    <div className="flex h-full w-64 flex-col border-r bg-card">
      {/* Logo */}
      <div className="flex h-16 items-center border-b px-6">
        <Link href="/dashboard" className="flex items-center space-x-2">
          <Video className="h-8 w-8 text-primary" />
          <span className="text-lg font-bold">NVP</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <item.icon className="h-5 w-5" />
              <span>{item.name}</span>
            </Link>
          );
        })}

        {isAdmin && (
          <>
            <div className="my-4 border-t" />
            {adminNavigation.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    "flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </>
        )}
      </nav>

      {/* System Status */}
      <div className="border-t p-4">
        <div className="rounded-lg bg-muted p-3">
          <div className="flex items-center space-x-2">
            <div className="h-2 w-2 rounded-full bg-green-500" />
            <span className="text-xs text-muted-foreground">System Healthy</span>
          </div>
        </div>
      </div>
    </div>
  );
}

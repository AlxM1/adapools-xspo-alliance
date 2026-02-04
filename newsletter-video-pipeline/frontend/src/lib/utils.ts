import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(date: string | Date): string {
  return new Date(date).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + "...";
}

export function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

export function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "completed":
    case "success":
    case "published":
      return "text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30";
    case "processing":
    case "in_progress":
    case "pending":
      return "text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900/30";
    case "failed":
    case "error":
      return "text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30";
    case "scheduled":
      return "text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900/30";
    default:
      return "text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-900/30";
  }
}

export function getPlatformIcon(platform: string): string {
  switch (platform.toLowerCase()) {
    case "youtube":
      return "/icons/youtube.svg";
    case "tiktok":
      return "/icons/tiktok.svg";
    case "instagram":
      return "/icons/instagram.svg";
    case "x":
    case "twitter":
      return "/icons/x.svg";
    default:
      return "/icons/default.svg";
  }
}

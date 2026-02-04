"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Video,
  Mic,
  User,
  PlayCircle,
  Clock,
  HardDrive,
  TrendingUp,
  Plus,
} from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { dashboardApi, pipelineApi, DashboardStats, PipelineJob } from "@/lib/api";
import { formatDateTime, formatDuration, getStatusColor } from "@/lib/utils";

function StatCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  description?: string;
  icon: any;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

function RecentPipelineCard({ pipeline }: { pipeline: PipelineJob }) {
  const router = useRouter();

  const statusVariant = () => {
    switch (pipeline.status) {
      case "completed":
        return "success";
      case "processing":
        return "info";
      case "failed":
        return "destructive";
      default:
        return "secondary";
    }
  };

  return (
    <div
      className="flex items-center justify-between rounded-lg border p-4 cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={() => router.push(`/pipeline/${pipeline.id}`)}
    >
      <div className="space-y-1">
        <p className="font-medium">{pipeline.newsletter_title}</p>
        <p className="text-sm text-muted-foreground">
          {formatDateTime(pipeline.created_at)}
        </p>
      </div>
      <div className="flex items-center space-x-4">
        {pipeline.status === "processing" && (
          <div className="w-24">
            <Progress value={pipeline.progress} className="h-2" />
          </div>
        )}
        <Badge variant={statusVariant()}>{pipeline.status}</Badge>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: dashboardApi.getStats,
    refetchInterval: 30000,
  });

  const { data: recentPipelines, isLoading: pipelinesLoading } = useQuery({
    queryKey: ["recent-pipelines"],
    queryFn: () => pipelineApi.list({ limit: 5 }),
    refetchInterval: 10000,
  });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
            <p className="text-muted-foreground">
              Overview of your newsletter video pipeline
            </p>
          </div>
          <Button onClick={() => router.push("/pipeline/new")}>
            <Plus className="mr-2 h-4 w-4" />
            New Pipeline
          </Button>
        </div>

        {/* Stats Grid */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Total Pipelines"
            value={stats?.total_pipelines || 0}
            description={`${stats?.completed_pipelines || 0} completed`}
            icon={PlayCircle}
          />
          <StatCard
            title="Videos Generated"
            value={stats?.total_videos || 0}
            icon={Video}
          />
          <StatCard
            title="Video Minutes"
            value={`${(stats?.video_minutes_generated || 0).toFixed(1)} min`}
            icon={Clock}
          />
          <StatCard
            title="Storage Used"
            value={`${(stats?.storage_used_mb || 0).toFixed(0)} MB`}
            icon={HardDrive}
          />
        </div>

        {/* Recent Pipelines */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Recent Pipelines</CardTitle>
                <CardDescription>
                  Your latest newsletter-to-video conversions
                </CardDescription>
              </div>
              <Button variant="outline" onClick={() => router.push("/pipeline")}>
                View All
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {pipelinesLoading ? (
              <div className="flex justify-center py-8">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              </div>
            ) : recentPipelines?.items && recentPipelines.items.length > 0 ? (
              <div className="space-y-3">
                {recentPipelines.items.map((pipeline) => (
                  <RecentPipelineCard key={pipeline.id} pipeline={pipeline} />
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <Video className="mx-auto h-12 w-12 text-muted-foreground" />
                <h3 className="mt-4 text-lg font-semibold">No pipelines yet</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Create your first pipeline to convert a newsletter into video
                </p>
                <Button
                  className="mt-4"
                  onClick={() => router.push("/pipeline/new")}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Create Pipeline
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="cursor-pointer hover:bg-accent/50 transition-colors" onClick={() => router.push("/voices")}>
            <CardHeader>
              <Mic className="h-8 w-8 text-primary" />
              <CardTitle className="mt-2">Voice Clones</CardTitle>
              <CardDescription>
                Manage your cloned voices for video narration
              </CardDescription>
            </CardHeader>
          </Card>
          <Card className="cursor-pointer hover:bg-accent/50 transition-colors" onClick={() => router.push("/avatars")}>
            <CardHeader>
              <User className="h-8 w-8 text-primary" />
              <CardTitle className="mt-2">AI Avatars</CardTitle>
              <CardDescription>
                Create and manage your AI avatar personas
              </CardDescription>
            </CardHeader>
          </Card>
          <Card className="cursor-pointer hover:bg-accent/50 transition-colors" onClick={() => router.push("/connections")}>
            <CardHeader>
              <TrendingUp className="h-8 w-8 text-primary" />
              <CardTitle className="mt-2">Social Connections</CardTitle>
              <CardDescription>
                Connect your social media accounts for publishing
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
}

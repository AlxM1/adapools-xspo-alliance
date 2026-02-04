"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  RefreshCw,
  XCircle,
  Download,
  Share2,
  CheckCircle,
  Clock,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { pipelineApi, videoApi } from "@/lib/api";
import { formatDateTime, formatDuration, formatBytes } from "@/lib/utils";
import { toast } from "sonner";

const stageOrder = ["script", "voice", "avatar", "video_process", "publish"];

function StageItem({
  stage,
  status,
  isActive,
}: {
  stage: string;
  status: string;
  isActive: boolean;
}) {
  const getIcon = () => {
    switch (status) {
      case "completed":
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case "processing":
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
      case "failed":
        return <AlertCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Clock className="h-5 w-5 text-muted-foreground" />;
    }
  };

  const stageName = {
    script: "Script Generation",
    voice: "Voice Synthesis",
    avatar: "Avatar Animation",
    video_process: "Video Processing",
    publish: "Publishing",
  }[stage] || stage;

  return (
    <div
      className={`flex items-center space-x-3 p-3 rounded-lg ${
        isActive ? "bg-blue-50 dark:bg-blue-900/20" : ""
      }`}
    >
      {getIcon()}
      <span className={isActive ? "font-medium" : ""}>{stageName}</span>
    </div>
  );
}

export default function PipelineDetailPage() {
  const router = useRouter();
  const params = useParams();
  const queryClient = useQueryClient();
  const id = params.id as string;

  const { data: pipeline, isLoading } = useQuery({
    queryKey: ["pipeline", id],
    queryFn: () => pipelineApi.get(id),
    refetchInterval: (data) =>
      data?.status === "processing" || data?.status === "pending" ? 3000 : false,
  });

  const cancelMutation = useMutation({
    mutationFn: () => pipelineApi.cancel(id),
    onSuccess: () => {
      toast.success("Pipeline cancelled");
      queryClient.invalidateQueries({ queryKey: ["pipeline", id] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to cancel pipeline");
    },
  });

  const retryMutation = useMutation({
    mutationFn: () => pipelineApi.retry(id),
    onSuccess: () => {
      toast.success("Pipeline restarted");
      queryClient.invalidateQueries({ queryKey: ["pipeline", id] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to retry pipeline");
    },
  });

  const getStageStatus = (stageName: string) => {
    const stage = pipeline?.stages?.find((s: any) => s.name === stageName);
    return stage?.status || "pending";
  };

  if (isLoading) {
    return (
      <DashboardLayout>
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      </DashboardLayout>
    );
  }

  if (!pipeline) {
    return (
      <DashboardLayout>
        <div className="text-center py-12">
          <h2 className="text-2xl font-bold">Pipeline not found</h2>
          <Button className="mt-4" onClick={() => router.push("/pipeline")}>
            Back to Pipelines
          </Button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Button variant="ghost" size="icon" onClick={() => router.back()}>
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="text-2xl font-bold">{pipeline.newsletter_title}</h1>
              <p className="text-muted-foreground">
                Created {formatDateTime(pipeline.created_at)}
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {pipeline.status === "processing" && (
              <Button
                variant="destructive"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
              >
                <XCircle className="mr-2 h-4 w-4" />
                Cancel
              </Button>
            )}
            {pipeline.status === "failed" && (
              <Button
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                Retry
              </Button>
            )}
          </div>
        </div>

        {/* Status and Progress */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Pipeline Status</CardTitle>
              <Badge
                variant={
                  pipeline.status === "completed"
                    ? "success"
                    : pipeline.status === "failed"
                    ? "destructive"
                    : pipeline.status === "processing"
                    ? "info"
                    : "secondary"
                }
              >
                {pipeline.status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {(pipeline.status === "processing" || pipeline.status === "pending") && (
              <div className="mb-6">
                <div className="flex justify-between text-sm mb-2">
                  <span>Overall Progress</span>
                  <span>{pipeline.progress}%</span>
                </div>
                <Progress value={pipeline.progress} className="h-3" />
              </div>
            )}

            {pipeline.error_message && (
              <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-lg">
                <p className="font-medium">Error</p>
                <p className="text-sm mt-1">{pipeline.error_message}</p>
              </div>
            )}

            <div className="space-y-2">
              <h4 className="font-medium mb-3">Pipeline Stages</h4>
              {stageOrder.map((stage) => (
                <StageItem
                  key={stage}
                  stage={stage}
                  status={getStageStatus(stage)}
                  isActive={pipeline.current_stage === stage}
                />
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Generated Videos */}
        {pipeline.videos && pipeline.videos.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Generated Videos</CardTitle>
              <CardDescription>
                Videos created from your newsletter content
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2">
                {pipeline.videos.map((video: any) => (
                  <Card key={video.id}>
                    <CardContent className="pt-6">
                      <div className="aspect-video bg-muted rounded-lg mb-4 overflow-hidden">
                        {video.thumbnail_url ? (
                          <img
                            src={video.thumbnail_url}
                            alt={video.title}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-muted-foreground">
                            No thumbnail
                          </div>
                        )}
                      </div>
                      <h4 className="font-medium">{video.title}</h4>
                      <div className="flex items-center space-x-4 text-sm text-muted-foreground mt-2">
                        <span>{formatDuration(video.duration_sec)}</span>
                        <span>{formatBytes(video.file_size)}</span>
                        <span>{video.format}</span>
                      </div>
                      <div className="flex space-x-2 mt-4">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={async () => {
                            const blob = await videoApi.download(video.id);
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `${video.title}.${video.format}`;
                            a.click();
                          }}
                        >
                          <Download className="mr-2 h-4 w-4" />
                          Download
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => router.push(`/videos/${video.id}`)}
                        >
                          <Share2 className="mr-2 h-4 w-4" />
                          Publish
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
}

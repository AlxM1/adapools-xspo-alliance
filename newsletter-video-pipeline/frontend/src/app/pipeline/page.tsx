"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Plus, Search, Filter } from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { pipelineApi, PipelineJob } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { useState } from "react";

function PipelineCard({ pipeline }: { pipeline: PipelineJob }) {
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
    <Card
      className="cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={() => router.push(`/pipeline/${pipeline.id}`)}
    >
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <h3 className="font-semibold">{pipeline.newsletter_title}</h3>
            <p className="text-sm text-muted-foreground">
              Created {formatDateTime(pipeline.created_at)}
            </p>
            {pipeline.current_stage && pipeline.status === "processing" && (
              <p className="text-sm text-muted-foreground">
                Stage: {pipeline.current_stage}
              </p>
            )}
          </div>
          <Badge variant={statusVariant()}>{pipeline.status}</Badge>
        </div>
        {pipeline.status === "processing" && (
          <div className="mt-4">
            <div className="flex justify-between text-sm mb-1">
              <span>Progress</span>
              <span>{pipeline.progress}%</span>
            </div>
            <Progress value={pipeline.progress} className="h-2" />
          </div>
        )}
        {pipeline.error_message && (
          <p className="mt-2 text-sm text-destructive">{pipeline.error_message}</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function PipelineListPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const { data: pipelines, isLoading } = useQuery({
    queryKey: ["pipelines", statusFilter],
    queryFn: () =>
      pipelineApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 50,
      }),
    refetchInterval: 10000,
  });

  const filteredPipelines = pipelines?.items?.filter((p) =>
    p.newsletter_title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Pipelines</h1>
            <p className="text-muted-foreground">
              View and manage your newsletter-to-video conversions
            </p>
          </div>
          <Button onClick={() => router.push("/pipeline/new")}>
            <Plus className="mr-2 h-4 w-4" />
            New Pipeline
          </Button>
        </div>

        {/* Filters */}
        <div className="flex items-center space-x-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search pipelines..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40">
              <Filter className="mr-2 h-4 w-4" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="processing">Processing</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Pipeline List */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        ) : filteredPipelines && filteredPipelines.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredPipelines.map((pipeline) => (
              <PipelineCard key={pipeline.id} pipeline={pipeline} />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <h3 className="text-lg font-semibold">No pipelines found</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                {searchQuery
                  ? "Try adjusting your search"
                  : "Create your first pipeline to get started"}
              </p>
              {!searchQuery && (
                <Button className="mt-4" onClick={() => router.push("/pipeline/new")}>
                  <Plus className="mr-2 h-4 w-4" />
                  Create Pipeline
                </Button>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
}

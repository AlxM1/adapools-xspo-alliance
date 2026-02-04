"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Video, Download, Share2, Search, Filter } from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { videoApi, Video as VideoType } from "@/lib/api";
import { formatDateTime, formatDuration, formatBytes } from "@/lib/utils";

function VideoCard({ video }: { video: VideoType }) {
  const router = useRouter();

  return (
    <Card className="overflow-hidden">
      <div
        className="aspect-video bg-muted cursor-pointer"
        onClick={() => router.push(`/videos/${video.id}`)}
      >
        {video.thumbnail_url ? (
          <img
            src={video.thumbnail_url}
            alt={video.title}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Video className="h-12 w-12 text-muted-foreground" />
          </div>
        )}
      </div>
      <CardContent className="pt-4">
        <h3
          className="font-semibold cursor-pointer hover:text-primary"
          onClick={() => router.push(`/videos/${video.id}`)}
        >
          {video.title}
        </h3>
        <div className="flex items-center space-x-4 text-sm text-muted-foreground mt-2">
          <span>{formatDuration(video.duration_sec)}</span>
          <span>{formatBytes(video.file_size)}</span>
          <Badge variant="outline">{video.format}</Badge>
        </div>
        <p className="text-sm text-muted-foreground mt-2">
          {formatDateTime(video.created_at)}
        </p>
        <div className="flex space-x-2 mt-4">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
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
            className="flex-1"
            onClick={() => router.push(`/videos/${video.id}`)}
          >
            <Share2 className="mr-2 h-4 w-4" />
            Publish
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function VideosPage() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [formatFilter, setFormatFilter] = useState("all");

  const { data: videos, isLoading } = useQuery({
    queryKey: ["videos"],
    queryFn: () => videoApi.list({ limit: 50 }),
  });

  const filteredVideos = videos?.items?.filter((video) => {
    const matchesSearch = video.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFormat = formatFilter === "all" || video.format === formatFilter;
    return matchesSearch && matchesFormat;
  });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Videos</h1>
          <p className="text-muted-foreground">
            Browse and manage your generated videos
          </p>
        </div>

        {/* Filters */}
        <div className="flex items-center space-x-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search videos..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={formatFilter} onValueChange={setFormatFilter}>
            <SelectTrigger className="w-40">
              <Filter className="mr-2 h-4 w-4" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Formats</SelectItem>
              <SelectItem value="mp4">MP4</SelectItem>
              <SelectItem value="webm">WebM</SelectItem>
              <SelectItem value="mov">MOV</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Video Grid */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        ) : filteredVideos && filteredVideos.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredVideos.map((video) => (
              <VideoCard key={video.id} video={video} />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Video className="h-12 w-12 text-muted-foreground" />
              <h3 className="mt-4 text-lg font-semibold">No videos found</h3>
              <p className="mt-2 text-sm text-muted-foreground text-center">
                {searchQuery
                  ? "Try adjusting your search"
                  : "Create a pipeline to generate videos from your newsletters"}
              </p>
              {!searchQuery && (
                <Button className="mt-4" onClick={() => router.push("/pipeline/new")}>
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

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  TrendingDown,
  Eye,
  Heart,
  MessageCircle,
  Share2,
  Clock,
  BarChart3,
  Calendar,
} from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/lib/api";

interface DashboardMetric {
  value: number;
  change: number;
}

interface DashboardOverview {
  period: string;
  metrics: {
    views: DashboardMetric;
    likes: DashboardMetric;
    comments: DashboardMetric;
    engagement_rate: DashboardMetric;
    watch_time_hours: DashboardMetric;
  };
  top_video: string | null;
  platform_breakdown: Record<string, Record<string, number>>;
}

function MetricCard({
  title,
  value,
  change,
  icon: Icon,
  format = "number",
}: {
  title: string;
  value: number;
  change: number;
  icon: any;
  format?: "number" | "percent" | "hours";
}) {
  const formatValue = (val: number) => {
    if (format === "percent") return `${val.toFixed(1)}%`;
    if (format === "hours") return `${val.toFixed(1)}h`;
    if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
    if (val >= 1000) return `${(val / 1000).toFixed(1)}K`;
    return val.toLocaleString();
  };

  const isPositive = change >= 0;

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-3xl font-bold mt-1">{formatValue(value)}</p>
            <div className={`flex items-center mt-2 text-sm ${isPositive ? "text-green-600" : "text-red-600"}`}>
              {isPositive ? <TrendingUp className="h-4 w-4 mr-1" /> : <TrendingDown className="h-4 w-4 mr-1" />}
              <span>{Math.abs(change).toFixed(1)}% vs last period</span>
            </div>
          </div>
          <div className="p-3 bg-primary/10 rounded-full">
            <Icon className="h-6 w-6 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const [period, setPeriod] = useState("7d");

  const { data: overview, isLoading } = useQuery<DashboardOverview>({
    queryKey: ["analytics-overview", period],
    queryFn: async () => {
      const response = await api.get(`/analytics/dashboard/overview?period=${period}`);
      return response.data;
    },
  });

  const { data: postingTimes } = useQuery({
    queryKey: ["posting-times"],
    queryFn: async () => {
      const response = await api.get("/analytics/posting-times/youtube");
      return response.data;
    },
  });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
            <p className="text-muted-foreground">
              Track performance across all platforms
            </p>
          </div>
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1d">Last 24h</SelectItem>
              <SelectItem value="7d">Last 7 days</SelectItem>
              <SelectItem value="30d">Last 30 days</SelectItem>
              <SelectItem value="90d">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Metrics Grid */}
        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            {[...Array(5)].map((_, i) => (
              <Card key={i}>
                <CardContent className="pt-6">
                  <div className="h-24 animate-pulse bg-muted rounded" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : overview && (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            <MetricCard
              title="Total Views"
              value={overview.metrics.views.value}
              change={overview.metrics.views.change}
              icon={Eye}
            />
            <MetricCard
              title="Likes"
              value={overview.metrics.likes.value}
              change={overview.metrics.likes.change}
              icon={Heart}
            />
            <MetricCard
              title="Comments"
              value={overview.metrics.comments.value}
              change={overview.metrics.comments.change}
              icon={MessageCircle}
            />
            <MetricCard
              title="Engagement Rate"
              value={overview.metrics.engagement_rate.value}
              change={overview.metrics.engagement_rate.change}
              icon={TrendingUp}
              format="percent"
            />
            <MetricCard
              title="Watch Time"
              value={overview.metrics.watch_time_hours.value}
              change={overview.metrics.watch_time_hours.change}
              icon={Clock}
              format="hours"
            />
          </div>
        )}

        {/* Tabs */}
        <Tabs defaultValue="performance">
          <TabsList>
            <TabsTrigger value="performance">Performance</TabsTrigger>
            <TabsTrigger value="posting">Best Times</TabsTrigger>
            <TabsTrigger value="ab-tests">A/B Tests</TabsTrigger>
            <TabsTrigger value="trends">Trends</TabsTrigger>
          </TabsList>

          <TabsContent value="performance" className="mt-4">
            <div className="grid gap-4 md:grid-cols-2">
              {/* Platform Breakdown */}
              <Card>
                <CardHeader>
                  <CardTitle>Platform Breakdown</CardTitle>
                  <CardDescription>Views by platform</CardDescription>
                </CardHeader>
                <CardContent>
                  {overview?.platform_breakdown && (
                    <div className="space-y-4">
                      {Object.entries(overview.platform_breakdown).map(([platform, metrics]) => (
                        <div key={platform} className="flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                              <BarChart3 className="h-4 w-4 text-primary" />
                            </div>
                            <span className="font-medium capitalize">{platform}</span>
                          </div>
                          <div className="text-right">
                            <p className="font-bold">{metrics.views?.toLocaleString() || 0}</p>
                            <p className="text-sm text-muted-foreground">views</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Top Performing Content */}
              <Card>
                <CardHeader>
                  <CardTitle>Top Performing</CardTitle>
                  <CardDescription>Your best content this period</CardDescription>
                </CardHeader>
                <CardContent>
                  {overview?.top_video ? (
                    <div className="text-center py-4">
                      <p className="text-lg font-medium">Video ID: {overview.top_video}</p>
                      <Button className="mt-4" variant="outline">
                        View Details
                      </Button>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No data available for this period
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="posting" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Optimal Posting Times</CardTitle>
                <CardDescription>
                  Based on your audience engagement patterns
                </CardDescription>
              </CardHeader>
              <CardContent>
                {postingTimes?.recommended_times ? (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {postingTimes.recommended_times.map((time: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-4 border rounded-lg"
                      >
                        <div className="flex items-center space-x-3">
                          <Calendar className="h-5 w-5 text-primary" />
                          <div>
                            <p className="font-medium capitalize">{time.day}</p>
                            <p className="text-sm text-muted-foreground">
                              {time.hour}:00 {time.hour >= 12 ? "PM" : "AM"}
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-medium text-green-600">
                            {(time.score * 100).toFixed(0)}% optimal
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    Loading posting time recommendations...
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="ab-tests" className="mt-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>A/B Tests</CardTitle>
                    <CardDescription>
                      Test different thumbnails, titles, and posting times
                    </CardDescription>
                  </div>
                  <Button>Create Test</Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-center py-12 text-muted-foreground">
                  <BarChart3 className="h-12 w-12 mx-auto mb-4" />
                  <p>No A/B tests running</p>
                  <p className="text-sm mt-2">Create a test to optimize your content performance</p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="trends" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Trending Topics</CardTitle>
                <CardDescription>
                  Topics gaining traction in your niche
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-center py-12 text-muted-foreground">
                  <TrendingUp className="h-12 w-12 mx-auto mb-4" />
                  <p>Trend detection coming soon</p>
                  <p className="text-sm mt-2">
                    We&apos;ll analyze trending topics to help you create timely content
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}

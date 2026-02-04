"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Rss,
  Mail,
  Webhook,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle,
  Clock,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import api from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { toast } from "sonner";

interface RSSFeed {
  id: string;
  name: string;
  url: string;
  check_interval_minutes: number;
  auto_process: boolean;
  is_active: boolean;
  last_checked: string | null;
  items_ingested: number;
}

interface EmailSource {
  id: string;
  name: string;
  imap_server: string;
  folder: string;
  is_active: boolean;
  last_checked: string | null;
  emails_ingested: number;
}

interface ContentItem {
  id: string;
  title: string;
  source_type: string;
  ingested_at: string;
  score: number;
  status: string;
}

export default function SourcesPage() {
  const queryClient = useQueryClient();
  const [isRssDialogOpen, setIsRssDialogOpen] = useState(false);
  const [isEmailDialogOpen, setIsEmailDialogOpen] = useState(false);
  const [newRss, setNewRss] = useState({ name: "", url: "", check_interval_minutes: 60 });
  const [newEmail, setNewEmail] = useState({
    name: "",
    imap_server: "",
    imap_port: 993,
    username: "",
    password: "",
    folder: "INBOX",
  });

  const { data: rssFeeds, isLoading: rssLoading } = useQuery<RSSFeed[]>({
    queryKey: ["rss-feeds"],
    queryFn: async () => {
      const response = await api.get("/content-ingestion/rss/feeds");
      return response.data;
    },
  });

  const { data: emailSources, isLoading: emailLoading } = useQuery<EmailSource[]>({
    queryKey: ["email-sources"],
    queryFn: async () => {
      const response = await api.get("/content-ingestion/email/sources");
      return response.data;
    },
  });

  const { data: contentItems } = useQuery<ContentItem[]>({
    queryKey: ["content-items"],
    queryFn: async () => {
      const response = await api.get("/content-ingestion/content?limit=20");
      return response.data;
    },
  });

  const addRssFeed = useMutation({
    mutationFn: async () => {
      const response = await api.post("/content-ingestion/rss/feeds", newRss);
      return response.data;
    },
    onSuccess: () => {
      toast.success("RSS feed added successfully");
      queryClient.invalidateQueries({ queryKey: ["rss-feeds"] });
      setIsRssDialogOpen(false);
      setNewRss({ name: "", url: "", check_interval_minutes: 60 });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to add RSS feed");
    },
  });

  const deleteRssFeed = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/content-ingestion/rss/feeds/${id}`);
    },
    onSuccess: () => {
      toast.success("RSS feed deleted");
      queryClient.invalidateQueries({ queryKey: ["rss-feeds"] });
    },
  });

  const checkRssFeed = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/content-ingestion/rss/feeds/${id}/check`);
    },
    onSuccess: () => {
      toast.success("Checking feed...");
      queryClient.invalidateQueries({ queryKey: ["rss-feeds"] });
    },
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "processing":
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      case "failed":
        return <AlertCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Content Sources</h1>
            <p className="text-muted-foreground">
              Automatically ingest newsletters from RSS, Email, and Webhooks
            </p>
          </div>
        </div>

        <Tabs defaultValue="rss">
          <TabsList>
            <TabsTrigger value="rss">
              <Rss className="h-4 w-4 mr-2" />
              RSS Feeds
            </TabsTrigger>
            <TabsTrigger value="email">
              <Mail className="h-4 w-4 mr-2" />
              Email
            </TabsTrigger>
            <TabsTrigger value="webhooks">
              <Webhook className="h-4 w-4 mr-2" />
              Webhooks
            </TabsTrigger>
            <TabsTrigger value="queue">
              Content Queue
            </TabsTrigger>
          </TabsList>

          {/* RSS Feeds Tab */}
          <TabsContent value="rss" className="mt-4 space-y-4">
            <div className="flex justify-end">
              <Dialog open={isRssDialogOpen} onOpenChange={setIsRssDialogOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <Plus className="mr-2 h-4 w-4" />
                    Add RSS Feed
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add RSS Feed</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Name</Label>
                      <Input
                        value={newRss.name}
                        onChange={(e) => setNewRss({ ...newRss, name: e.target.value })}
                        placeholder="My Newsletter"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Feed URL</Label>
                      <Input
                        value={newRss.url}
                        onChange={(e) => setNewRss({ ...newRss, url: e.target.value })}
                        placeholder="https://example.com/feed.xml"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Check Interval (minutes)</Label>
                      <Input
                        type="number"
                        value={newRss.check_interval_minutes}
                        onChange={(e) => setNewRss({ ...newRss, check_interval_minutes: parseInt(e.target.value) })}
                        min={5}
                        max={1440}
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setIsRssDialogOpen(false)}>Cancel</Button>
                    <Button onClick={() => addRssFeed.mutate()} disabled={!newRss.name || !newRss.url}>
                      Add Feed
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>

            {rssLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin" />
              </div>
            ) : rssFeeds && rssFeeds.length > 0 ? (
              <div className="grid gap-4">
                {rssFeeds.map((feed) => (
                  <Card key={feed.id}>
                    <CardContent className="pt-6">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-4">
                          <div className="p-2 bg-orange-100 rounded-lg">
                            <Rss className="h-5 w-5 text-orange-600" />
                          </div>
                          <div>
                            <h3 className="font-semibold">{feed.name}</h3>
                            <p className="text-sm text-muted-foreground">{feed.url}</p>
                            <div className="flex items-center space-x-4 mt-1 text-sm">
                              <span>{feed.items_ingested} items ingested</span>
                              {feed.last_checked && (
                                <span>Last checked: {formatDateTime(feed.last_checked)}</span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Badge variant={feed.is_active ? "success" : "secondary"}>
                            {feed.is_active ? "Active" : "Paused"}
                          </Badge>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => checkRssFeed.mutate(feed.id)}
                          >
                            <RefreshCw className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => deleteRssFeed.mutate(feed.id)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <Rss className="h-12 w-12 text-muted-foreground" />
                  <h3 className="mt-4 text-lg font-semibold">No RSS feeds configured</h3>
                  <p className="mt-2 text-sm text-muted-foreground text-center">
                    Add an RSS feed to automatically ingest newsletter content
                  </p>
                  <Button className="mt-4" onClick={() => setIsRssDialogOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    Add RSS Feed
                  </Button>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Email Tab */}
          <TabsContent value="email" className="mt-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Email Sources</CardTitle>
                    <CardDescription>
                      Connect email accounts to auto-ingest newsletters
                    </CardDescription>
                  </div>
                  <Button>
                    <Plus className="mr-2 h-4 w-4" />
                    Add Email Source
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {emailSources && emailSources.length > 0 ? (
                  <div className="space-y-4">
                    {emailSources.map((source) => (
                      <div key={source.id} className="flex items-center justify-between p-4 border rounded-lg">
                        <div className="flex items-center space-x-4">
                          <Mail className="h-5 w-5 text-blue-600" />
                          <div>
                            <p className="font-medium">{source.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {source.imap_server} / {source.folder}
                            </p>
                          </div>
                        </div>
                        <Badge variant={source.is_active ? "success" : "secondary"}>
                          {source.emails_ingested} emails
                        </Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Mail className="h-12 w-12 mx-auto mb-4" />
                    <p>No email sources configured</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Webhooks Tab */}
          <TabsContent value="webhooks" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Webhook Endpoints</CardTitle>
                <CardDescription>
                  Use these URLs to send content from external tools
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 bg-muted rounded-lg">
                  <p className="text-sm font-medium mb-2">Generic Webhook</p>
                  <code className="text-sm bg-background p-2 rounded block">
                    POST /api/content-ingestion/webhooks/ingest
                  </code>
                </div>
                <div className="p-4 bg-muted rounded-lg">
                  <p className="text-sm font-medium mb-2">Zapier Webhook</p>
                  <code className="text-sm bg-background p-2 rounded block">
                    POST /api/content-ingestion/webhooks/zapier
                  </code>
                </div>
                <div className="p-4 bg-muted rounded-lg">
                  <p className="text-sm font-medium mb-2">n8n Webhook</p>
                  <code className="text-sm bg-background p-2 rounded block">
                    POST /api/content-ingestion/webhooks/n8n
                  </code>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Content Queue Tab */}
          <TabsContent value="queue" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Content Queue</CardTitle>
                <CardDescription>
                  Recently ingested content awaiting processing
                </CardDescription>
              </CardHeader>
              <CardContent>
                {contentItems && contentItems.length > 0 ? (
                  <div className="space-y-4">
                    {contentItems.map((item) => (
                      <div key={item.id} className="flex items-center justify-between p-4 border rounded-lg">
                        <div className="flex items-center space-x-4">
                          {getStatusIcon(item.status)}
                          <div>
                            <p className="font-medium">{item.title}</p>
                            <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                              <Badge variant="outline">{item.source_type}</Badge>
                              <span>Score: {item.score.toFixed(1)}</span>
                              <span>{formatDateTime(item.ingested_at)}</span>
                            </div>
                          </div>
                        </div>
                        <Button variant="outline" size="sm">
                          Process
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Clock className="h-12 w-12 mx-auto mb-4" />
                    <p>No content in queue</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}

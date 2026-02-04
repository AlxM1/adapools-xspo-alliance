"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Share2, Check, X, ExternalLink, Loader2 } from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { socialApi, SocialConnection } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { toast } from "sonner";

const platforms = [
  {
    id: "youtube",
    name: "YouTube",
    description: "Upload long-form videos and Shorts",
    color: "bg-red-500",
  },
  {
    id: "tiktok",
    name: "TikTok",
    description: "Share short-form vertical videos",
    color: "bg-black",
  },
  {
    id: "instagram",
    name: "Instagram",
    description: "Post Reels and video content",
    color: "bg-gradient-to-br from-purple-500 to-pink-500",
  },
  {
    id: "x",
    name: "X (Twitter)",
    description: "Share videos with your followers",
    color: "bg-black",
  },
];

function PlatformCard({
  platform,
  connection,
  onConnect,
  onDisconnect,
  isConnecting,
}: {
  platform: (typeof platforms)[0];
  connection?: SocialConnection;
  onConnect: () => void;
  onDisconnect: () => void;
  isConnecting: boolean;
}) {
  const isConnected = connection?.is_connected;

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-4">
            <div
              className={`flex h-12 w-12 items-center justify-center rounded-lg ${platform.color} text-white`}
            >
              <Share2 className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-semibold">{platform.name}</h3>
              <p className="text-sm text-muted-foreground">{platform.description}</p>
            </div>
          </div>
          <Badge variant={isConnected ? "success" : "secondary"}>
            {isConnected ? (
              <>
                <Check className="mr-1 h-3 w-3" />
                Connected
              </>
            ) : (
              <>
                <X className="mr-1 h-3 w-3" />
                Not Connected
              </>
            )}
          </Badge>
        </div>

        {isConnected && connection && (
          <div className="mt-4 p-3 bg-muted rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">@{connection.username}</p>
                {connection.expires_at && (
                  <p className="text-xs text-muted-foreground">
                    Token expires: {formatDateTime(connection.expires_at)}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="mt-4">
          {isConnected ? (
            <Button
              variant="outline"
              className="w-full"
              onClick={onDisconnect}
            >
              Disconnect
            </Button>
          ) : (
            <Button
              className="w-full"
              onClick={onConnect}
              disabled={isConnecting}
            >
              {isConnecting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Connect {platform.name}
              <ExternalLink className="ml-2 h-4 w-4" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function ConnectionsPage() {
  const queryClient = useQueryClient();

  const { data: connections, isLoading } = useQuery({
    queryKey: ["social-connections"],
    queryFn: socialApi.getConnections,
  });

  const connectMutation = useMutation({
    mutationFn: async (platform: string) => {
      const { auth_url } = await socialApi.getAuthUrl(platform);
      window.open(auth_url, "_blank", "width=600,height=700");
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to initiate connection");
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: socialApi.disconnect,
    onSuccess: () => {
      toast.success("Platform disconnected");
      queryClient.invalidateQueries({ queryKey: ["social-connections"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to disconnect");
    },
  });

  const getConnection = (platformId: string): SocialConnection | undefined => {
    return connections?.find((c) => c.platform === platformId);
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Social Connections</h1>
          <p className="text-muted-foreground">
            Connect your social media accounts to enable auto-publishing
          </p>
        </div>

        {/* Platform Grid */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {platforms.map((platform) => (
              <PlatformCard
                key={platform.id}
                platform={platform}
                connection={getConnection(platform.id)}
                onConnect={() => connectMutation.mutate(platform.id)}
                onDisconnect={() => disconnectMutation.mutate(platform.id)}
                isConnecting={connectMutation.isPending}
              />
            ))}
          </div>
        )}

        {/* Info Card */}
        <Card>
          <CardHeader>
            <CardTitle>About OAuth Connections</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-muted-foreground">
            <p>
              We use OAuth to securely connect to your social media accounts. This means:
            </p>
            <ul className="list-disc list-inside space-y-2">
              <li>We never see or store your passwords</li>
              <li>You can revoke access at any time</li>
              <li>We only request permissions needed for publishing videos</li>
              <li>Your credentials are stored encrypted</li>
            </ul>
            <p>
              After connecting, you can use the auto-publish feature to automatically
              post your videos when they&apos;re ready.
            </p>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}

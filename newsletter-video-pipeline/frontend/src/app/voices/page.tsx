"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { Mic, Plus, Trash2, Star, Upload, Loader2 } from "lucide-react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { voiceApi, Voice } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { toast } from "sonner";

const languages = [
  { code: "en", name: "English" },
  { code: "es", name: "Spanish" },
  { code: "fr", name: "French" },
  { code: "de", name: "German" },
  { code: "it", name: "Italian" },
  { code: "pt", name: "Portuguese" },
  { code: "pl", name: "Polish" },
  { code: "tr", name: "Turkish" },
  { code: "ru", name: "Russian" },
  { code: "nl", name: "Dutch" },
  { code: "cs", name: "Czech" },
  { code: "ar", name: "Arabic" },
  { code: "zh", name: "Chinese" },
  { code: "ja", name: "Japanese" },
  { code: "ko", name: "Korean" },
  { code: "hu", name: "Hungarian" },
  { code: "hi", name: "Hindi" },
];

function VoiceCard({ voice, onDelete, onSetDefault }: { voice: Voice; onDelete: () => void; onSetDefault: () => void }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <Mic className="h-6 w-6 text-primary" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-semibold">{voice.name}</h3>
                {voice.is_default && <Badge variant="secondary">Default</Badge>}
              </div>
              <p className="text-sm text-muted-foreground">
                {languages.find((l) => l.code === voice.language)?.name || voice.language}
              </p>
            </div>
          </div>
          <div className="flex space-x-2">
            {!voice.is_default && (
              <Button variant="ghost" size="icon" onClick={onSetDefault}>
                <Star className="h-4 w-4" />
              </Button>
            )}
            <Button variant="ghost" size="icon" onClick={onDelete}>
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        </div>
        <div className="mt-4 text-sm text-muted-foreground">
          Created {formatDateTime(voice.created_at)}
        </div>
        {voice.sample_url && (
          <audio controls className="w-full mt-4">
            <source src={voice.sample_url} type="audio/wav" />
          </audio>
        )}
      </CardContent>
    </Card>
  );
}

export default function VoicesPage() {
  const queryClient = useQueryClient();
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("en");
  const [audioFiles, setAudioFiles] = useState<File[]>([]);

  const { data: voices, isLoading } = useQuery({
    queryKey: ["voices"],
    queryFn: voiceApi.list,
  });

  const createVoice = useMutation({
    mutationFn: async () => {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("language", language);
      audioFiles.forEach((file) => formData.append("audio_files", file));
      return voiceApi.create(formData);
    },
    onSuccess: () => {
      toast.success("Voice clone created successfully");
      queryClient.invalidateQueries({ queryKey: ["voices"] });
      setIsDialogOpen(false);
      setName("");
      setAudioFiles([]);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to create voice clone");
    },
  });

  const deleteVoice = useMutation({
    mutationFn: voiceApi.delete,
    onSuccess: () => {
      toast.success("Voice deleted");
      queryClient.invalidateQueries({ queryKey: ["voices"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to delete voice");
    },
  });

  const setDefaultVoice = useMutation({
    mutationFn: voiceApi.setDefault,
    onSuccess: () => {
      toast.success("Default voice updated");
      queryClient.invalidateQueries({ queryKey: ["voices"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to set default voice");
    },
  });

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "audio/*": [".wav", ".mp3", ".m4a", ".flac"],
    },
    onDrop: (acceptedFiles) => {
      setAudioFiles((prev) => [...prev, ...acceptedFiles]);
    },
  });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Voice Clones</h1>
            <p className="text-muted-foreground">
              Create and manage cloned voices for video narration
            </p>
          </div>
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                Clone Voice
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Create Voice Clone</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Voice Name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My Voice"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Language</Label>
                  <Select value={language} onValueChange={setLanguage}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {languages.map((lang) => (
                        <SelectItem key={lang.code} value={lang.code}>
                          {lang.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Audio Samples</Label>
                  <div
                    {...getRootProps()}
                    className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                      isDragActive ? "border-primary bg-primary/10" : "border-muted-foreground/25"
                    }`}
                  >
                    <input {...getInputProps()} />
                    <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground">
                      Drag & drop audio files here, or click to select
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      30+ seconds of clear speech recommended
                    </p>
                  </div>
                  {audioFiles.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {audioFiles.map((file, index) => (
                        <div
                          key={index}
                          className="flex items-center justify-between text-sm p-2 bg-muted rounded"
                        >
                          <span>{file.name}</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setAudioFiles((prev) => prev.filter((_, i) => i !== index))
                            }
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => createVoice.mutate()}
                  disabled={!name || audioFiles.length === 0 || createVoice.isPending}
                >
                  {createVoice.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Create Voice
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Voice List */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        ) : voices?.items && voices.items.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {voices.items.map((voice) => (
              <VoiceCard
                key={voice.id}
                voice={voice}
                onDelete={() => deleteVoice.mutate(voice.id)}
                onSetDefault={() => setDefaultVoice.mutate(voice.id)}
              />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Mic className="h-12 w-12 text-muted-foreground" />
              <h3 className="mt-4 text-lg font-semibold">No voice clones yet</h3>
              <p className="mt-2 text-sm text-muted-foreground text-center">
                Upload audio samples of your voice to create a clone
              </p>
              <Button className="mt-4" onClick={() => setIsDialogOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Clone Voice
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Tips */}
        <Card>
          <CardHeader>
            <CardTitle>Tips for Better Voice Clones</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc list-inside space-y-2 text-sm text-muted-foreground">
              <li>Use high-quality audio recordings (WAV or FLAC preferred)</li>
              <li>Record at least 30 seconds of clear speech</li>
              <li>Avoid background noise and music</li>
              <li>Speak naturally and at a consistent pace</li>
              <li>Multiple samples (2-3) can improve quality</li>
              <li>Include various emotions and tones for versatility</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}

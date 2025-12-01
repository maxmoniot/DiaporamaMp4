import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import axios from "axios";
import { Reorder } from "framer-motion";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  Music,
  Play,
  Pause,
  Settings,
  Download,
  Trash2,
  ImageIcon,
  Wand2,
  GripVertical,
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  Volume2,
  VolumeX,
  SkipBack,
  Timer,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function HomePage() {
  const [project, setProject] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [exportStatus, setExportStatus] = useState(null);
  const [isMuted, setIsMuted] = useState(false);
  const [selectedPhotoId, setSelectedPhotoId] = useState(null);
  const [globalDuration, setGlobalDuration] = useState(2);
  const [isDownloading, setIsDownloading] = useState(false);
  
  const audioRef = useRef(null);
  const playIntervalRef = useRef(null);
  const photoStartTimesRef = useRef([]);

  // Initialize project
  useEffect(() => {
    initProject();
    return () => {
      if (playIntervalRef.current) clearInterval(playIntervalRef.current);
    };
  }, []);

  const initProject = async () => {
    try {
      // Check for existing project in localStorage
      const savedProjectId = localStorage.getItem("photosync_project_id");
      
      if (savedProjectId) {
        try {
          const response = await axios.get(`${API}/projects/${savedProjectId}`);
          setProject(response.data);
          setIsLoading(false);
          return;
        } catch {
          localStorage.removeItem("photosync_project_id");
        }
      }
      
      // Create new project
      const response = await axios.post(`${API}/projects`);
      setProject(response.data);
      localStorage.setItem("photosync_project_id", response.data.id);
    } catch (error) {
      toast.error("Erreur lors de l'initialisation du projet");
    } finally {
      setIsLoading(false);
    }
  };

  const refreshProject = async () => {
    if (!project?.id) return;
    try {
      const response = await axios.get(`${API}/projects/${project.id}`);
      setProject(response.data);
    } catch (error) {
      console.error("Error refreshing project:", error);
    }
  };

  // Calculate photo start times for preview
  useEffect(() => {
    if (project?.photos) {
      const sortedPhotos = [...project.photos].sort((a, b) => a.order - b.order);
      let cumulative = 0;
      const times = sortedPhotos.map((photo) => {
        const start = cumulative;
        cumulative += photo.duration;
        return start;
      });
      photoStartTimesRef.current = times;
    }
  }, [project?.photos]);

  // Photo upload handler
  const onPhotosDrop = useCallback(
    async (acceptedFiles) => {
      if (!project?.id) return;
      setIsUploading(true);
      
      try {
        const formData = new FormData();
        acceptedFiles.forEach((file) => {
          formData.append("files", file);
        });
        
        await axios.post(`${API}/projects/${project.id}/photos`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        
        await refreshProject();
        toast.success(`${acceptedFiles.length} photo(s) ajoutée(s)`);
      } catch (error) {
        toast.error("Erreur lors de l'upload des photos");
      } finally {
        setIsUploading(false);
      }
    },
    [project?.id]
  );

  const {
    getRootProps: getPhotoRootProps,
    getInputProps: getPhotoInputProps,
    isDragActive: isPhotoDragActive,
  } = useDropzone({
    onDrop: onPhotosDrop,
    accept: {
      "image/*": [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"],
    },
    multiple: true,
  });

  // Music upload handler
  const onMusicDrop = useCallback(
    async (acceptedFiles) => {
      if (!project?.id || acceptedFiles.length === 0) return;
      setIsUploading(true);
      
      try {
        const formData = new FormData();
        formData.append("file", acceptedFiles[0]);
        
        await axios.post(`${API}/projects/${project.id}/music`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        
        await refreshProject();
        toast.success("Musique ajoutée - Tempo analysé !");
      } catch (error) {
        toast.error("Erreur lors de l'upload de la musique");
      } finally {
        setIsUploading(false);
      }
    },
    [project?.id]
  );

  const {
    getRootProps: getMusicRootProps,
    getInputProps: getMusicInputProps,
    isDragActive: isMusicDragActive,
  } = useDropzone({
    onDrop: onMusicDrop,
    accept: { "audio/mpeg": [".mp3"] },
    multiple: false,
  });

  // Sync to beats
  const syncToBeats = async () => {
    if (!project?.id) return;
    try {
      await axios.post(`${API}/projects/${project.id}/sync-to-beats`);
      await refreshProject();
      toast.success("Photos synchronisées sur le tempo !");
    } catch (error) {
      toast.error("Erreur lors de la synchronisation");
    }
  };

  // Update settings
  const updateSettings = async (key, value) => {
    if (!project?.id) return;
    try {
      await axios.put(`${API}/projects/${project.id}/settings`, { [key]: value });
      await refreshProject();
    } catch (error) {
      toast.error("Erreur lors de la mise à jour");
    }
  };

  // Apply global duration to all photos
  const applyGlobalDuration = async () => {
    if (!project?.id || !sortedPhotos.length) return;
    try {
      await axios.put(`${API}/projects/${project.id}/photos/duration/all`, {
        duration: globalDuration,
      });
      await refreshProject();
      toast.success(`Durée de ${globalDuration}s appliquée à toutes les photos`);
    } catch (error) {
      toast.error("Erreur lors de la mise à jour");
    }
  };

  // Reorder photos
  const handleReorder = async (newOrder) => {
    if (!project?.id) return;
    
    const updatedPhotos = newOrder.map((photo, index) => ({
      ...photo,
      order: index,
    }));
    
    setProject((prev) => ({ ...prev, photos: updatedPhotos }));
    
    try {
      await axios.put(`${API}/projects/${project.id}/photos/reorder`, {
        photo_ids: newOrder.map((p) => p.id),
      });
    } catch (error) {
      toast.error("Erreur lors du réordonnancement");
      await refreshProject();
    }
  };

  // Delete photo
  const deletePhoto = async (photoId) => {
    if (!project?.id) return;
    try {
      await axios.delete(`${API}/projects/${project.id}/photos/${photoId}`);
      await refreshProject();
      toast.success("Photo supprimée");
    } catch (error) {
      toast.error("Erreur lors de la suppression");
    }
  };

  // Update photo duration
  const updatePhotoDuration = async (photoId, duration) => {
    if (!project?.id) return;
    try {
      await axios.put(`${API}/projects/${project.id}/photos/duration`, {
        photo_id: photoId,
        duration: duration,
      });
      await refreshProject();
    } catch (error) {
      toast.error("Erreur lors de la mise à jour");
    }
  };

  // Preview controls
  const getTotalDuration = () => {
    if (!project?.photos) return 0;
    return project.photos.reduce((sum, p) => sum + p.duration, 0);
  };

  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
      if (audioRef.current) audioRef.current.pause();
      if (playIntervalRef.current) clearInterval(playIntervalRef.current);
    } else {
      setIsPlaying(true);
      if (audioRef.current && project?.music) {
        audioRef.current.currentTime = currentTime;
        audioRef.current.play().catch(() => {});
      }
      
      playIntervalRef.current = setInterval(() => {
        setCurrentTime((prev) => {
          const total = getTotalDuration();
          if (prev >= total) {
            setIsPlaying(false);
            if (audioRef.current) audioRef.current.pause();
            clearInterval(playIntervalRef.current);
            return 0;
          }
          return prev + 0.05;
        });
      }, 50);
    }
  };

  const resetPreview = () => {
    setIsPlaying(false);
    setCurrentTime(0);
    setCurrentPhotoIndex(0);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    if (playIntervalRef.current) clearInterval(playIntervalRef.current);
  };

  // Update current photo based on time
  useEffect(() => {
    const times = photoStartTimesRef.current;
    if (!times.length) return;
    
    let idx = 0;
    for (let i = 0; i < times.length; i++) {
      if (currentTime >= times[i]) idx = i;
    }
    setCurrentPhotoIndex(idx);
  }, [currentTime]);

  // Export handlers
  const startExport = async () => {
    if (!project?.id) return;
    setShowExportDialog(true);
    setExportStatus({ status: "processing", progress: 0 });
    
    try {
      await axios.post(`${API}/projects/${project.id}/export`);
      
      // Poll for status
      const pollStatus = setInterval(async () => {
        try {
          const response = await axios.get(
            `${API}/projects/${project.id}/export/status`
          );
          setExportStatus(response.data);
          
          if (
            response.data.status === "completed" ||
            response.data.status === "error"
          ) {
            clearInterval(pollStatus);
          }
        } catch (error) {
          clearInterval(pollStatus);
        }
      }, 1000);
    } catch (error) {
      toast.error("Erreur lors de l'export");
      setExportStatus({ status: "error" });
    }
  };

  const downloadExport = () => {
    if (!project?.id) return;
    setIsDownloading(true);
    
    // Use direct link download
    const downloadUrl = `${API}/projects/${project.id}/export/download`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = 'photosync_video.mp4';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    setTimeout(() => {
      setIsDownloading(false);
      toast.success("Téléchargement démarré !");
    }, 500);
  };

  // Sorted photos
  const sortedPhotos = project?.photos
    ? [...project.photos].sort((a, b) => a.order - b.order)
    : [];

  const currentPhoto = sortedPhotos[currentPhotoIndex];
  const currentFormat = project?.settings?.format || "horizontal";
  const currentTransition = project?.settings?.transition || "none";

  // Get preview URL - use the preview with blurred background
  const getPreviewUrl = (photo) => {
    if (!photo) return null;
    if (photo.preview) {
      return `${API}/previews/${photo.preview}`;
    }
    return `${API}/photos/${photo.filename}`;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" data-testid="loading-screen">
        <Loader2 className="w-12 h-12 text-indigo-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col" data-testid="home-page">
      {/* Noise overlay */}
      <div className="noise-overlay" />
      
      {/* Header */}
      <header className="glass fixed top-0 left-0 right-0 z-50 px-6 py-4" data-testid="header">
        <div className="flex items-center justify-between max-w-screen-2xl mx-auto">
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-indigo-400">Photo</span>Sync
          </h1>
          
          <div className="flex items-center gap-4">
            {project?.music && (
              <div className="flex items-center gap-2 text-sm text-zinc-400">
                <Music className="w-4 h-4" />
                <span className="mono">{Math.round(project.music.tempo)} BPM</span>
              </div>
            )}
            
            <Button
              onClick={startExport}
              disabled={!sortedPhotos.length}
              className="bg-indigo-500 hover:bg-indigo-600 text-white gap-2"
              data-testid="export-btn"
            >
              <Download className="w-4 h-4" />
              Exporter MP4
            </Button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 pt-20 pb-40 px-6">
        <div className="max-w-screen-2xl mx-auto">
          {sortedPhotos.length === 0 ? (
            /* Empty state - Large dropzone */
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8" data-testid="empty-state">
              <div
                {...getPhotoRootProps()}
                className={`dropzone w-full max-w-3xl p-16 flex flex-col items-center justify-center cursor-pointer ${isPhotoDragActive ? "active" : ""}`}
                data-testid="photo-dropzone"
              >
                <input {...getPhotoInputProps()} data-testid="photo-input" />
                {isUploading ? (
                  <Loader2 className="w-16 h-16 text-indigo-500 animate-spin" />
                ) : (
                  <>
                    <div className="w-24 h-24 rounded-full bg-zinc-800 flex items-center justify-center mb-6">
                      <Upload className="w-10 h-10 text-indigo-400" />
                    </div>
                    <h2 className="text-2xl font-bold mb-2">Déposez vos photos ici</h2>
                    <p className="text-zinc-400 text-center">
                      Glissez-déposez vos photos ou cliquez pour sélectionner
                      <br />
                      <span className="text-sm">JPG, PNG, WebP • Jusqu'à 500+ photos</span>
                    </p>
                  </>
                )}
              </div>
              
              <div
                {...getMusicRootProps()}
                className={`dropzone w-full max-w-xl p-8 flex items-center justify-center gap-4 cursor-pointer ${isMusicDragActive ? "active" : ""}`}
                data-testid="music-dropzone"
              >
                <input {...getMusicInputProps()} data-testid="music-input" />
                <Music className="w-8 h-8 text-zinc-400" />
                <div>
                  <p className="font-medium">Ajouter une musique</p>
                  <p className="text-sm text-zinc-500">MP3 • Le tempo sera analysé automatiquement</p>
                </div>
              </div>
            </div>
          ) : (
            /* Content state - Split view */
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Left: Media Library */}
              <div className="space-y-6">
                {/* Upload zones */}
                <div className="grid grid-cols-2 gap-4">
                  <div
                    {...getPhotoRootProps()}
                    className={`dropzone p-4 flex items-center justify-center gap-3 cursor-pointer ${isPhotoDragActive ? "active" : ""}`}
                    data-testid="photo-dropzone-small"
                  >
                    <input {...getPhotoInputProps()} />
                    <ImageIcon className="w-5 h-5 text-zinc-400" />
                    <span className="text-sm">+ Photos</span>
                  </div>
                  
                  <div
                    {...getMusicRootProps()}
                    className={`dropzone p-4 flex items-center justify-center gap-3 cursor-pointer ${isMusicDragActive ? "active" : ""}`}
                    data-testid="music-dropzone-small"
                  >
                    <input {...getMusicInputProps()} />
                    <Music className="w-5 h-5 text-zinc-400" />
                    <span className="text-sm">
                      {project?.music ? project.music.original_name.slice(0, 15) + "..." : "+ Musique"}
                    </span>
                  </div>
                </div>

                {/* Music info & sync */}
                {project?.music && (
                  <div className="card p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-indigo-500/20 flex items-center justify-center">
                        <Music className="w-5 h-5 text-indigo-400" />
                      </div>
                      <div>
                        <p className="font-medium text-sm">{project.music.original_name}</p>
                        <p className="text-xs text-zinc-500 mono">
                          {Math.round(project.music.tempo)} BPM • {Math.floor(project.music.duration / 60)}:{String(Math.floor(project.music.duration % 60)).padStart(2, "0")}
                        </p>
                      </div>
                    </div>
                    <Button
                      onClick={syncToBeats}
                      variant="outline"
                      className="gap-2 border-indigo-500/50 text-indigo-400 hover:bg-indigo-500/10"
                      data-testid="sync-beats-btn"
                    >
                      <Wand2 className="w-4 h-4" />
                      Synchro tempo
                    </Button>
                  </div>
                )}

                {/* Settings panel */}
                <div className="card p-6 space-y-6" data-testid="settings-panel">
                  <h3 className="font-bold flex items-center gap-2">
                    <Settings className="w-4 h-4" />
                    Paramètres
                  </h3>
                  
                  <div className="grid grid-cols-2 gap-4">
                    {/* Format */}
                    <div className="space-y-2">
                      <label className="text-sm text-zinc-400">Format</label>
                      <Select
                        value={project?.settings?.format || "horizontal"}
                        onValueChange={(v) => updateSettings("format", v)}
                      >
                        <SelectTrigger className="w-full bg-zinc-900 border-zinc-700" data-testid="format-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-900 border-zinc-700">
                          <SelectItem value="horizontal">Horizontal (16:9)</SelectItem>
                          <SelectItem value="vertical">Vertical (9:16)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    {/* Resolution */}
                    <div className="space-y-2">
                      <label className="text-sm text-zinc-400">Résolution</label>
                      <Select
                        value={project?.settings?.resolution || "1080p"}
                        onValueChange={(v) => updateSettings("resolution", v)}
                      >
                        <SelectTrigger className="w-full bg-zinc-900 border-zinc-700" data-testid="resolution-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-900 border-zinc-700">
                          <SelectItem value="720p">720p (HD)</SelectItem>
                          <SelectItem value="1080p">1080p (Full HD)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    {/* Transition */}
                    <div className="space-y-2">
                      <label className="text-sm text-zinc-400">Transition</label>
                      <Select
                        value={project?.settings?.transition || "none"}
                        onValueChange={(v) => updateSettings("transition", v)}
                      >
                        <SelectTrigger className="w-full bg-zinc-900 border-zinc-700" data-testid="transition-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-900 border-zinc-700">
                          <SelectItem value="none">Aucune (cut)</SelectItem>
                          <SelectItem value="fade">Fondu enchaîné</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    {/* Rhythm multiplier */}
                    <div className="space-y-2">
                      <label className="text-sm text-zinc-400">Multiplicateur rythme</label>
                      <Select
                        value={String(project?.settings?.global_rhythm_multiplier || 1)}
                        onValueChange={(v) => updateSettings("global_rhythm_multiplier", parseFloat(v))}
                      >
                        <SelectTrigger className="w-full bg-zinc-900 border-zinc-700" data-testid="rhythm-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-zinc-900 border-zinc-700">
                          <SelectItem value="0.5">x0.5 (rapide)</SelectItem>
                          <SelectItem value="1">x1 (normal)</SelectItem>
                          <SelectItem value="2">x2 (lent)</SelectItem>
                          <SelectItem value="4">x4 (très lent)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  
                  {/* Global duration control */}
                  <div className="pt-4 border-t border-zinc-800">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-2">
                        <Timer className="w-4 h-4 text-zinc-400" />
                        <span className="text-sm text-zinc-400">Durée par photo</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Input
                          type="number"
                          step="0.1"
                          min="0.5"
                          max="30"
                          value={globalDuration}
                          onChange={(e) => setGlobalDuration(parseFloat(e.target.value) || 2)}
                          className="w-20 bg-zinc-900 border-zinc-700 text-center"
                          data-testid="global-duration-input"
                        />
                        <span className="text-sm text-zinc-500">sec</span>
                        <Button
                          onClick={applyGlobalDuration}
                          variant="outline"
                          size="sm"
                          className="border-zinc-700 hover:bg-zinc-800"
                          data-testid="apply-global-duration-btn"
                        >
                          Appliquer à tout
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Stats */}
                <div className="flex items-center justify-between text-sm text-zinc-400">
                  <span>{sortedPhotos.length} photos</span>
                  <span className="mono">
                    Durée totale: {Math.floor(getTotalDuration() / 60)}:{String(Math.floor(getTotalDuration() % 60)).padStart(2, "0")}
                  </span>
                </div>
              </div>

              {/* Right: Preview */}
              <div className="space-y-4">
                {/* Preview container */}
                <div
                  className={`card overflow-hidden bg-black relative ${
                    currentFormat === "vertical"
                      ? "preview-vertical max-w-[300px] mx-auto"
                      : "preview-horizontal"
                  }`}
                  data-testid="preview-container"
                >
                  {currentPhoto ? (
                    <div
                      key={`${currentPhoto.id}-${currentPhotoIndex}`}
                      className="absolute inset-0"
                      style={{
                        animation: `kenburns ${currentPhoto.duration}s linear`,
                      }}
                    >
                      <img
                        src={getPreviewUrl(currentPhoto)}
                        alt=""
                        className="w-full h-full object-contain"
                      />
                    </div>
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center text-zinc-600">
                      <ImageIcon className="w-16 h-16" />
                    </div>
                  )}
                  
                  {/* Time overlay */}
                  <div className="absolute bottom-4 right-4 bg-black/70 px-3 py-1 rounded-full text-sm mono z-10">
                    {Math.floor(currentTime / 60)}:{String(Math.floor(currentTime % 60)).padStart(2, "0")} / 
                    {Math.floor(getTotalDuration() / 60)}:{String(Math.floor(getTotalDuration() % 60)).padStart(2, "0")}
                  </div>
                  
                  {/* Photo counter */}
                  <div className="absolute top-4 left-4 bg-black/70 px-3 py-1 rounded-full text-sm mono z-10">
                    {currentPhotoIndex + 1} / {sortedPhotos.length}
                  </div>
                </div>

                {/* Preview controls */}
                <div className="card p-4 flex items-center justify-center gap-4" data-testid="preview-controls">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={resetPreview}
                    data-testid="reset-btn"
                  >
                    <SkipBack className="w-5 h-5" />
                  </Button>
                  
                  <Button
                    onClick={togglePlay}
                    className="w-14 h-14 rounded-full bg-indigo-500 hover:bg-indigo-600"
                    data-testid="play-btn"
                  >
                    {isPlaying ? (
                      <Pause className="w-6 h-6" />
                    ) : (
                      <Play className="w-6 h-6 ml-1" />
                    )}
                  </Button>
                  
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setIsMuted(!isMuted)}
                    data-testid="mute-btn"
                  >
                    {isMuted ? (
                      <VolumeX className="w-5 h-5" />
                    ) : (
                      <Volume2 className="w-5 h-5" />
                    )}
                  </Button>
                </div>

                {/* Progress bar */}
                <div className="card p-4">
                  <Slider
                    value={[currentTime]}
                    max={getTotalDuration() || 1}
                    step={0.1}
                    onValueChange={([v]) => {
                      setCurrentTime(v);
                      if (audioRef.current) audioRef.current.currentTime = v;
                    }}
                    className="w-full"
                    data-testid="progress-slider"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Timeline */}
      {sortedPhotos.length > 0 && (
        <div className="timeline-track fixed bottom-0 left-0 right-0 h-36 px-6 py-4" data-testid="timeline">
          <ScrollArea className="h-full w-full">
            <Reorder.Group
              axis="x"
              values={sortedPhotos}
              onReorder={handleReorder}
              className="flex gap-3 h-full items-center pb-2"
            >
              {sortedPhotos.map((photo, index) => (
                <Reorder.Item
                  key={photo.id}
                  value={photo}
                  className={`timeline-item relative flex-shrink-0 w-24 h-24 cursor-grab active:cursor-grabbing ${
                    currentPhotoIndex === index ? "selected" : ""
                  } ${selectedPhotoId === photo.id ? "ring-2 ring-indigo-500" : ""}`}
                  onClick={() => setSelectedPhotoId(photo.id)}
                  data-testid={`timeline-item-${index}`}
                >
                  <img
                    src={`${API}/thumbnails/${photo.thumbnail}`}
                    alt=""
                    className="w-full h-full object-cover"
                    draggable={false}
                  />
                  
                  {/* Duration badge */}
                  <div className="absolute bottom-1 right-1 bg-black/70 px-1.5 py-0.5 rounded text-xs mono">
                    {photo.duration.toFixed(1)}s
                  </div>
                  
                  {/* Delete button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deletePhoto(photo.id);
                    }}
                    className="absolute top-1 right-1 w-5 h-5 bg-red-500/80 rounded-full flex items-center justify-center opacity-0 hover:opacity-100 focus:opacity-100"
                    data-testid={`delete-photo-${index}`}
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                  
                  {/* Drag handle */}
                  <div className="absolute top-1 left-1 text-white/50">
                    <GripVertical className="w-4 h-4" />
                  </div>
                  
                  {/* Orientation indicator */}
                  {photo.orientation === "portrait" && (
                    <div className="absolute bottom-1 left-1 bg-indigo-500/70 px-1 py-0.5 rounded text-[10px]">
                      V
                    </div>
                  )}
                </Reorder.Item>
              ))}
            </Reorder.Group>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
          
          {/* Selected photo duration control */}
          {selectedPhotoId && (
            <div className="absolute top-0 right-6 transform -translate-y-full bg-zinc-900 border border-zinc-700 rounded-t-lg p-3 flex items-center gap-3">
              <Clock className="w-4 h-4 text-zinc-400" />
              <span className="text-sm">Durée:</span>
              <input
                type="number"
                step="0.1"
                min="0.5"
                max="30"
                value={sortedPhotos.find((p) => p.id === selectedPhotoId)?.duration || 2}
                onChange={(e) => updatePhotoDuration(selectedPhotoId, parseFloat(e.target.value))}
                className="input-field w-20 text-sm"
                data-testid="duration-input"
              />
              <span className="text-sm text-zinc-500">sec</span>
            </div>
          )}
        </div>
      )}

      {/* Hidden audio element */}
      {project?.music && (
        <audio
          ref={audioRef}
          src={`${API}/music/${project.music.filename}`}
          muted={isMuted}
          preload="auto"
        />
      )}

      {/* Export dialog */}
      <Dialog open={showExportDialog} onOpenChange={setShowExportDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-700" data-testid="export-dialog" aria-describedby="export-dialog-description">
          <DialogHeader>
            <DialogTitle>Export vidéo</DialogTitle>
          </DialogHeader>
          <p id="export-dialog-description" className="sr-only">Fenêtre d'export de la vidéo MP4</p>
          
          <div className="py-6">
            {exportStatus?.status === "processing" && (
              <div className="space-y-4">
                <div className="flex items-center justify-center">
                  <Loader2 className="w-12 h-12 text-indigo-500 animate-spin" />
                </div>
                <p className="text-center text-zinc-400">Génération en cours...</p>
                <Progress value={exportStatus.progress} className="h-2" />
                <p className="text-center text-sm mono">{Math.round(exportStatus.progress)}%</p>
              </div>
            )}
            
            {exportStatus?.status === "completed" && (
              <div className="space-y-4 text-center">
                <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto" />
                <p className="text-lg font-medium">Export terminé !</p>
                <Button
                  onClick={downloadExport}
                  disabled={isDownloading}
                  className="bg-indigo-500 hover:bg-indigo-600 gap-2"
                  data-testid="download-btn"
                >
                  {isDownloading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  Télécharger la vidéo
                </Button>
              </div>
            )}
            
            {exportStatus?.status === "error" && (
              <div className="space-y-4 text-center">
                <XCircle className="w-16 h-16 text-red-500 mx-auto" />
                <p className="text-lg font-medium">Erreur lors de l'export</p>
                <p className="text-sm text-zinc-400">Veuillez réessayer</p>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

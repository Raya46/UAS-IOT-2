import { useState, useRef, useEffect } from "react";
import { uploadVideo, getUploadStatus } from "../../services/api";

type UploadState = "idle" | "uploading" | "processing" | "completed" | "failed";

export function VideoUploadPanel() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [syncedCount, setSyncedCount] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleFile = (file: File | null) => {
    if (file && file.name.endsWith(".mp4")) {
      setSelectedFile(file);
      setUploadState("idle");
      setErrorMsg(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploadState("uploading");
    setUploadProgress(10);
    setErrorMsg(null);

    try {
      const result = await uploadVideo(selectedFile);
      setUploadProgress(50);
      setUploadState("processing");

      pollRef.current = setInterval(async () => {
        try {
          const status = await getUploadStatus(result.job_id);
          if (status.status === "completed") {
            setUploadState("completed");
            setUploadProgress(100);
            setSyncedCount(status.synced_count || 0);
            if (pollRef.current) clearInterval(pollRef.current);
          } else if (status.status === "failed") {
            setUploadState("failed");
            setErrorMsg(status.error || "Processing failed");
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          setUploadState("failed");
          setErrorMsg("Status check failed");
        }
      }, 2000);
    } catch (err: any) {
      setUploadState("failed");
      setErrorMsg(err?.message || "Upload failed");
    }
  };

  const reset = () => {
    setSelectedFile(null);
    setUploadState("idle");
    setUploadProgress(0);
    setSyncedCount(0);
    setErrorMsg(null);
    if (pollRef.current) clearInterval(pollRef.current);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">upload_file</span>
          <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">Import Video</h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {uploadState === "idle" && (
          <>
            <div
              ref={dropRef}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-outline-variant rounded-2xl p-8 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-all"
            >
              <span className="material-symbols-outlined text-[36px] text-on-surface-variant mb-2">upload</span>
              <p className="text-[12px] text-on-surface-variant font-medium">
                {selectedFile ? selectedFile.name : "Klik untuk pilih file .mp4"}
              </p>
              {selectedFile && (
                <p className="text-[10px] text-on-surface-variant mt-1">
                  {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
                </p>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".mp4"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
            <button
              onClick={handleUpload}
              disabled={!selectedFile}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-primary text-white text-[12px] font-bold rounded-xl disabled:bg-outline disabled:text-on-surface-variant disabled:cursor-not-allowed hover:brightness-105 transition-all"
            >
              <span className="material-symbols-outlined text-[16px]">upload</span>
              Upload & Proses
            </button>
          </>
        )}

        {uploadState === "uploading" && (
          <div className="flex flex-col gap-3 py-8 items-center">
            <span className="material-symbols-outlined text-[28px] text-primary animate-spin">sync</span>
            <span className="text-[13px] font-semibold text-on-surface">Mengupload video...</span>
            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
              <div className="bg-primary h-full rounded-full transition-all" style={{ width: `${uploadProgress}%` }} />
            </div>
          </div>
        )}

        {uploadState === "processing" && (
          <div className="flex flex-col gap-3 py-8 items-center">
            <span className="material-symbols-outlined text-[28px] text-cyan-600 animate-spin">radar</span>
            <span className="text-[13px] font-semibold text-on-surface">AI menganalisis video...</span>
            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
              <div className="bg-cyan-500 h-full rounded-full animate-pulse" style={{ width: "60%" }} />
            </div>
            <p className="text-[10px] text-on-surface-variant text-center">Proses memakan waktu beberapa menit</p>
          </div>
        )}

        {uploadState === "completed" && (
          <div className="flex flex-col gap-4 py-4 items-center">
            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-6 text-center w-full">
              <span className="material-symbols-outlined text-[36px] text-emerald-600">check_circle</span>
              <p className="text-emerald-700 font-bold text-[16px] mt-2">Selesai</p>
              <p className="text-[12px] text-emerald-600 mt-1">
                {syncedCount > 0
                  ? `${syncedCount} pelanggaran ditemukan`
                  : "Tidak ada pelanggaran terdeteksi"}
              </p>
            </div>
            <button
              onClick={reset}
              className="w-full py-2.5 bg-primary text-white text-[12px] font-bold rounded-xl hover:brightness-105 transition-all"
            >
              Upload Lagi
            </button>
          </div>
        )}

        {uploadState === "failed" && (
          <div className="flex flex-col gap-4 py-4 items-center">
            <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center w-full">
              <span className="material-symbols-outlined text-[36px] text-red-500">error</span>
              <p className="text-red-700 font-bold text-[16px] mt-2">Gagal</p>
              <p className="text-[11px] text-red-600 mt-1">{errorMsg || "Terjadi kesalahan"}</p>
            </div>
            <div className="flex gap-2 w-full">
              <button
                onClick={() => setUploadState("idle")}
                className="flex-1 py-2.5 bg-white border border-outline-variant text-on-surface text-[12px] font-bold rounded-xl hover:bg-slate-50 transition-all"
              >
                Coba Lagi
              </button>
              <button
                onClick={reset}
                className="flex-1 py-2.5 bg-primary text-white text-[12px] font-bold rounded-xl hover:brightness-105 transition-all"
              >
                Tutup
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

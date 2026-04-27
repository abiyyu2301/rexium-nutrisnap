"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import styles from "./page.module.css";
import CalorieRing from "./components/CalorieRing";
import MacroCard from "./components/MacroCard";
import FoodRow from "./components/FoodRow";
import InsightPanel from "./components/InsightPanel";
import InsightChip from "./components/InsightChip";
import DropzoneCard from "./components/DropzoneCard";
import CameraCapture, { triggerCamera } from "./components/CameraCapture";
import LoadingState from "./components/LoadingState";
import RecentCard from "./components/RecentCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
const RDA_CALORIES = 2000;
const RECENT_KEY = "nutrisnap_recent";
const MAX_RECENT = 3;

interface IdentifiedFood {
  raw_name: string;
  matched_name: string | null;
  calories_kcal: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  fiber_g: number | null;
  confidence: number;
  source: string | null;
}

interface NutritionSummary {
  total_calories_kcal: number;
  total_protein_g: number;
  total_carbs_g: number;
  total_fat_g: number;
  total_fiber_g: number;
}

interface AnalysisResult {
  analysis_id: string;
  identified_foods: IdentifiedFood[];
  nutrition_summary: NutritionSummary;
}

interface RecentAnalysis {
  id: string;
  previewUrl: string;
  totalCalories: number;
  foods: string[];
  timestamp: number;
}

type AppState = "idle" | "confirming" | "loading" | "result" | "error";

// ── localStorage helpers ──────────────────────────────────────────────────────

function loadRecent(): RecentAnalysis[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveRecent(items: RecentAnalysis[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, MAX_RECENT)));
  } catch {
    // ignore quota errors
  }
}

function addRecent(item: RecentAnalysis) {
  const existing = loadRecent().filter((r) => r.id !== item.id);
  saveRecent([item, ...existing]);
}

// ── Calorie color helper ──────────────────────────────────────────────────────

function calorieColor(current: number, target: number = RDA_CALORIES) {
  const pct = (current / target) * 100;
  if (pct > 100) return "over";
  if (pct > 85) return "warn";
  return "";
}

// ── Timestamp helper ──────────────────────────────────────────────────────────

function formatTimestamp(ts: number) {
  const d = new Date(ts);
  return d.toLocaleTimeString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  });
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function HomePage() {
  const [state, setState] = useState<AppState>("idle");
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [recent, setRecent] = useState<RecentAnalysis[]>([]);
  // Confirming state: held file + description
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [description, setDescription] = useState<string>("");
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);

  // Load recent on mount
  useEffect(() => {
    setRecent(loadRecent());
  }, []);

  const analyzeImage = useCallback(async (file: File, descriptionText: string) => {
    setState("loading");
    setPreview(URL.createObjectURL(file));
    setErrorMsg("");

    const formData = new FormData();
    formData.append("image", file);
    if (descriptionText.trim()) {
      formData.append("description", descriptionText.trim());
    }

    try {
      const res = await fetch(`${API_URL}/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data: AnalysisResult = await res.json();
      setResult(data);
      setState("result");

      // Save to recent
      const previewUrl = URL.createObjectURL(file);
      const recentItem: RecentAnalysis = {
        id: data.analysis_id,
        previewUrl,
        totalCalories: data.nutrition_summary.total_calories_kcal,
        foods: data.identified_foods.map(
          (f) => f.matched_name || f.raw_name
        ),
        timestamp: Date.now(),
      };
      addRecent(recentItem);
      setRecent(loadRecent());
    } catch (e: any) {
      setErrorMsg(
        e?.message || "Analisis gagal. Coba foto ulang dengan cahaya lebih baik."
      );
      setState("error");
    }
  }, []);

  const handleFileSelected = useCallback((file: File) => {
    // Show confirming screen with preview + description input
    setPendingFile(file);
    setPreview(URL.createObjectURL(file));
    setDescription("");
    setState("confirming");
  }, []);

  const handleConfirm = useCallback(() => {
    if (!pendingFile) return;
    analyzeImage(pendingFile, description);
  }, [pendingFile, description, analyzeImage]);

  const handleCancelConfirm = useCallback(() => {
    if (preview) URL.revokeObjectURL(preview);
    setPendingFile(null);
    setPreview(null);
    setDescription("");
    setState("idle");
  }, [preview]);

  const handleCameraFile = useCallback(
    (file: File) => handleFileSelected(file),
    [handleFileSelected]
  );

  const handleGalleryFile = useCallback(
    (file: File) => handleFileSelected(file),
    [handleFileSelected]
  );

  const handleCameraClick = () => {
    triggerCamera(cameraRef);
  };

  const handleGalleryClick = () => {
    triggerCamera(galleryRef);
  };

  const handleRecallRecent = (item: RecentAnalysis) => {
    // For now just show a toast-style message
    // In future: re-analyze or show cached result
    alert("Fitur recall sedang dalam pengembangan");
  };

  const reset = () => {
    if (preview) URL.revokeObjectURL(preview);
    setState("idle");
    setPreview(null);
    setResult(null);
    setErrorMsg("");
    setPendingFile(null);
    setDescription("");
  };

  const calorieClass = result
    ? calorieColor(result.nutrition_summary.total_calories_kcal)
    : "";

  return (
    <main className={styles.main}>
      {/* ── Hidden camera + gallery inputs ── */}
      <CameraCapture onFileSelected={handleCameraFile} inputRef={cameraRef} />
      {/* Gallery ref — no capture attr for gallery picker */}
      <input
        ref={galleryRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleGalleryFile(file);
          e.target.value = "";
        }}
        className={styles.hiddenInput}
        aria-label="Pilih dari galeri"
      />

      {/* ── Header ── */}
      <header className={styles.header}>
        <h1 className={styles.logo}>NutriSnap</h1>
      </header>

      {/* ── Idle ── */}
      {state === "idle" && (
        <div>
          <DropzoneCard
            onCameraClick={handleCameraClick}
            onGalleryClick={handleGalleryClick}
          />

          {/* Recent analyses */}
          {recent.length > 0 && (
            <div className={styles.recentSection}>
              <p className={styles.recentLabel}>Analisis Terbaru</p>
              {recent.map((item) => (
                <RecentCard
                  key={item.id}
                  item={item}
                  onRecall={handleRecallRecent}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Confirming (preview + description + submit) ── */}
      {state === "confirming" && preview && (
        <div className={styles.confirmSection}>
          <div className={styles.confirmImageWrapper}>
            <img src={preview} alt="Preview" className={styles.confirmImage} />
          </div>

          <div className={styles.descCard}>
            <label className={styles.descLabel} htmlFor="food-description">
              Detail makanan (opsional)
            </label>
            <p className={styles.descHint}>
              Contoh: nasi 100g, ayam goreng 150g, sambal 20g
            </p>
            <textarea
              id="food-description"
              className={styles.descInput}
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="nasi 100g, ayam goreng 150g, telur 50g, es teh 200ml"
            />
          </div>

          <div className={styles.confirmActions}>
            <button className={styles.cancelBtn} onClick={handleCancelConfirm}>
              Batal
            </button>
            <button className={styles.analyzeBtn} onClick={handleConfirm}>
              🔍 Analisis
            </button>
          </div>
        </div>
      )}

      {/* ── Loading ── */}
      {state === "loading" && <LoadingState previewUrl={preview} />}

      {/* ── Error ── */}
      {state === "error" && (
        <div className={styles.errorSection}>
          {preview && (
            <img
              src={preview!}
              alt="Preview"
              className={styles.resultImage}
            />
          )}
          <div className={styles.errorCard}>
            <p className={styles.errorIcon}>📸</p>
            <p className={styles.errorTitle}>Gagal menganalisis</p>
            <p className={styles.errorMsg}>{errorMsg}</p>
            <button className={styles.retryBtn} onClick={reset}>
              Coba Lagi
            </button>
          </div>
        </div>
      )}

      {/* ── Result ── */}
      {state === "result" && result && (
        <div className={styles.resultSection}>
          {/* Food image */}
          {preview && (
            <div className={`${styles.resultImageWrapper} anim-card`}>
              <img
                src={preview!}
                alt="Meal"
                className={styles.resultImage}
              />
              <span className={styles.resultBadge}>
                #{result.analysis_id.slice(0, 8)}
              </span>
              <span className={styles.resultTimestamp}>
                {formatTimestamp(Date.now())}
              </span>
            </div>
          )}

          {/* Calorie summary */}
          <div className={`${styles.calorieCard} anim-card`}>
            <div className={styles.calorieInfo}>
              <div className={`${styles.calorieNumber} ${styles[calorieClass]}`}>
                {result.nutrition_summary.total_calories_kcal}
              </div>
              <div className={styles.calorieKcal}>kkal</div>
              <div className={styles.calorieRda}>
                <span>
                  {Math.round(
                    (result.nutrition_summary.total_calories_kcal / RDA_CALORIES) * 100
                  )}
                  %
                </span>{" "}
                dari {RDA_CALORIES} kkal harian
              </div>
            </div>
            <CalorieRing
              current={result.nutrition_summary.total_calories_kcal}
              target={RDA_CALORIES}
              size={100}
            />
          </div>

          {/* Macro breakdown */}
          <MacroCard
            protein_g={result.nutrition_summary.total_protein_g}
            carbs_g={result.nutrition_summary.total_carbs_g}
            fat_g={result.nutrition_summary.total_fat_g}
            fiber_g={result.nutrition_summary.total_fiber_g}
          />

          {/* Food items */}
          <div className={`${styles.foodCard} anim-card`}>
            <p className={styles.foodCardTitle}>
              Makanan Terdeteksi ({result.identified_foods.length})
            </p>
            <ul className={styles.foodList}>
              {result.identified_foods.map((food, i) => (
                <FoodRow key={i} food={food} />
              ))}
            </ul>
          </div>

          {/* Health insights */}
          <InsightPanel summary={result.nutrition_summary} />

          {/* Actions */}
          <div className={styles.actionRow}>
            <button className={styles.anotherBtn} onClick={reset}>
              🍽️ Analisis Makanan Lain
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

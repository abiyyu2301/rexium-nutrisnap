"use client";

import { useState, useRef, useCallback } from "react";
import styles from "./page.module.css";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

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

type AppState = "idle" | "loading" | "result" | "error";

export default function HomePage() {
  const [state, setState] = useState<AppState>("idle");
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const analyzeImage = useCallback(async (file: File) => {
    setState("loading");
    setPreview(URL.createObjectURL(file));
    setErrorMsg("");

    const formData = new FormData();
    formData.append("image", file);

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
    } catch (e: any) {
      setErrorMsg(e.message || "Analisis gagal. Coba lagi.");
      setState("error");
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) analyzeImage(file);
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file && file.type.startsWith("image/")) analyzeImage(file);
    },
    [analyzeImage]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const file = e.clipboardData.files?.[0];
      if (file && file.type.startsWith("image/")) analyzeImage(file);
    },
    [analyzeImage]
  );

  const reset = () => {
    setState("idle");
    setPreview(null);
    setResult(null);
    setErrorMsg("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <main className={styles.main} onPaste={handlePaste}>
      <header className={styles.header}>
        <h1 className={styles.logo}>NutriSnap</h1>
        <p className={styles.tagline}>Foto makanannya. Ketahui Gizinya.</p>
      </header>

      {/* ── Idle: Upload UI ── */}
      {state === "idle" && (
        <div className={styles.uploadSection}>
          <div
            className={styles.dropzone}
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className={styles.dropzoneIcon}>
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9 22 9 12 15 12 15 22"/>
              </svg>
            </div>
            <p className={styles.dropzoneText}>
              Tap, drag &amp; drop, atau paste gambar makanan
            </p>
            <p className={styles.dropzoneSubtext}>JPG, PNG, WebP · max 10MB</p>
            <button className={styles.cameraBtn}>
              📷 Ambil Foto dengan Kamera
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handleFileChange}
              className={styles.hiddenInput}
            />
          </div>

          <div className={styles.recentSection}>
            <p className={styles.recentLabel}>Analisis Terbaru</p>
            <div className={styles.recentEmpty}>
              Belum ada analisis. Coba foto makanan pertamamu!
            </div>
          </div>
        </div>
      )}

      {/* ── Loading ── */}
      {state === "loading" && (
        <div className={styles.loadingSection}>
          {preview && (
            <img src={preview} alt="Preview" className={styles.previewImage} />
          )}
          <div className={styles.loadingCard}>
            <div className={styles.spinner} />
            <p className={styles.loadingText}>AI sedang menganalisis...</p>
            <p className={styles.loadingSubtext}>Mengahitung kalori dan nutrisi</p>
          </div>
        </div>
      )}

      {/* ── Error ── */}
      {state === "error" && (
        <div className={styles.errorSection}>
          {preview && (
            <img src={preview!} alt="Preview" className={styles.previewImage} />
          )}
          <div className={styles.errorCard}>
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
          {preview && (
            <img src={preview!} alt="Meal" className={styles.resultImage} />
          )}

          {/* Macro Summary */}
          <div className={styles.macroCard}>
            <div className={styles.calorieRing}>
              <span className={styles.calorieNumber}>
                {result.nutrition_summary.total_calories_kcal}
              </span>
              <span className={styles.calorieLabel}>kkal</span>
            </div>
            <div className={styles.macroBars}>
              <MacroBar label="Protein" value={result.nutrition_summary.total_protein_g} color="#4CAF50" unit="g" />
              <MacroBar label="Karbo" value={result.nutrition_summary.total_carbs_g} color="#FF9800" unit="g" />
              <MacroBar label="Lemak" value={result.nutrition_summary.total_fat_g} color="#F44336" unit="g" />
              <MacroBar label="Serat" value={result.nutrition_summary.total_fiber_g} color="#2196F3" unit="g" />
            </div>
          </div>

          {/* Per-item breakdown */}
          <div className={styles.foodList}>
            <h3 className={styles.foodListTitle}>Rincian per Makanan</h3>
            {result.identified_foods.map((food, i) => (
              <FoodRow key={i} food={food} />
            ))}
          </div>

          <button className={styles.anotherBtn} onClick={reset}>
            🍽️ Analisis Makanan Lain
          </button>
        </div>
      )}
    </main>
  );
}

function MacroBar({ label, value, color, unit }: { label: string; value: number; color: string; unit: string }) {
  // Max reasonable value for bar scaling
  const max = 100;
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className={styles.macroRow}>
      <span className={styles.macroLabel}>{label}</span>
      <div className={styles.macroTrack}>
        <div className={styles.macroFill} style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className={styles.macroValue}>{value.toFixed(1)}{unit}</span>
    </div>
  );
}

function FoodRow({ food }: { food: IdentifiedFood }) {
  const confidencePct = Math.round(food.confidence * 100);
  const confColor = confidencePct >= 80 ? "#4CAF50" : confidencePct >= 60 ? "#FF9800" : "#F44336";

  return (
    <div className={styles.foodRow}>
      <div className={styles.foodInfo}>
        <span className={styles.foodName}>{food.matched_name || food.raw_name}</span>
        {!food.matched_name && (
          <span className={styles.foodNoMatch}>⚠️ Tidak ditemukan di database</span>
        )}
        {food.matched_name && food.matched_name !== food.raw_name && (
          <span className={styles.foodRaw}>"{food.raw_name}"</span>
        )}
      </div>
      <div className={styles.foodNutrition}>
        {food.calories_kcal != null ? (
          <>
            <span className={styles.foodCal}>{food.calories_kcal} kkal</span>
            <span className={styles.foodMacros}>
              P:{food.protein_g?.toFixed(1) || "—"} C:{food.carbs_g?.toFixed(1) || "—"} F:{food.fat_g?.toFixed(1) || "—"}
            </span>
          </>
        ) : (
          <span className={styles.foodCal}>— kkal</span>
        )}
        <span className={styles.confBadge} style={{ color: confColor }}>
          {confidencePct}%
        </span>
      </div>
    </div>
  );
}

"use client";

import React from "react";

interface LoadingStateProps {
  previewUrl: string | null;
  progress?: boolean; // show indeterminate progress bar
}

export default function LoadingState({ previewUrl, progress = true }: LoadingStateProps) {
  return (
    <div className="loadingSection">
      {previewUrl && (
        <div className="loadingImageWrapper">
          <img
            src={previewUrl}
            alt="Preview"
            className="previewImage"
          />
          <div className="loadingOverlay">
            <div className="loadingSpinner" />
            <p className="loadingText">Menganalisis...</p>
            <p className="loadingSubtext">Mendeteksi makanan dan menghitung nutrisi</p>
            {progress && (
              <div className="loadingProgressBar">
                <div className="loadingProgressFill" />
              </div>
            )}
          </div>
        </div>
      )}

      {!previewUrl && (
        <div
          style={{
            background: "var(--surface)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-md)",
            padding: "48px 24px",
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "16px",
          }}
        >
          <div className="loadingSpinner" />
          <p className="loadingText">Menganalisis...</p>
          <p className="loadingSubtext">Mendeteksi makanan dan menghitung nutrisi</p>
          {progress && (
            <div style={{ width: "100%", maxWidth: "240px" }}>
              <div className="loadingProgressBar">
                <div className="loadingProgressFill" />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import React from "react";

interface DropzoneCardProps {
  onCameraClick: () => void;
  onGalleryClick: () => void;
}

export default function DropzoneCard({ onCameraClick, onGalleryClick }: DropzoneCardProps) {
  return (
    <div className="uploadSection">
      {/* Hero dropzone card */}
      <div className="dropzoneCard" onClick={onCameraClick} role="button" tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && onCameraClick()}>
        <div className="dropzoneIcon">
          {/* Camera SVG */}
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
            <circle cx="12" cy="13" r="4"/>
          </svg>
        </div>
        <p className="dropzoneTitle">Foto Makananmu</p>
        <p className="dropzoneSub">Kamera atau pilih dari galeri</p>

        <button
          className="cameraBtn"
          onClick={(e) => { e.stopPropagation(); onCameraClick(); }}
          type="button"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <circle cx="12" cy="12" r="4"/>
            <line x1="4.93" y1="4.93" x2="9.17" y2="9.17"/>
            <line x1="14.83" y1="14.83" x2="19.07" y2="19.07"/>
            <line x1="14.83" y1="9.17" x2="19.07" y2="4.93"/>
            <line x1="4.93" y1="19.07" x2="9.17" y2="14.83"/>
          </svg>
          Ambil Foto dengan Kamera
        </button>
      </div>

      {/* Divider */}
      <div className="divider">atau</div>

      {/* Gallery button */}
      <button
        className="galleryBtn"
        onClick={onGalleryClick}
        type="button"
      >
        📁 Pilih dari Galeri
      </button>

      <p className="pasteHint">💡 Tip: Paste gambar langsung dengan Ctrl+V</p>
    </div>
  );
}

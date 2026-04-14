"use client";

import React, { useRef } from "react";

interface CameraCaptureProps {
  onFileSelected: (file: File) => void;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}

/**
 * CameraCapture — opens device camera on mobile via capture="environment"
 * and also handles gallery selection as fallback.
 * Pass a ref to the hidden input if you need direct control.
 */
export default function CameraCapture({
  onFileSelected,
  inputRef,
}: CameraCaptureProps) {
  const internalRef = useRef<HTMLInputElement>(null);
  const ref = (inputRef as React.RefObject<HTMLInputElement>) || internalRef;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onFileSelected(file);
    // Reset so same file can be re-selected
    e.target.value = "";
  };

  return (
    <input
      ref={ref}
      type="file"
      accept="image/jpeg,image/png,image/webp"
      capture="environment"
      onChange={handleChange}
      className="hiddenInput"
      aria-label="Ambil foto atau pilih dari galeri"
    />
  );
}

/**
 * triggerCamera — programmatically click the hidden camera input.
 * Call this from a button's onClick.
 */
export function triggerCamera(ref: React.RefObject<HTMLInputElement | null>) {
  ref.current?.click();
}

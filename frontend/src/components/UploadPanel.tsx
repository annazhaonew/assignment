import { useCallback } from "react";

interface UploadPanelProps {
  onFileSelected: (file: File) => void;
  isLoading: boolean;
  fileName?: string;
}

export default function UploadPanel({
  onFileSelected,
  isLoading,
  fileName,
}: UploadPanelProps) {
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file && file.type === "application/pdf") onFileSelected(file);
    },
    [onFileSelected],
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onFileSelected(file);
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
        isLoading
          ? "border-indigo-300 bg-indigo-50"
          : "border-gray-300 hover:border-indigo-400 bg-white"
      }`}
    >
      {isLoading ? (
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin h-8 w-8 border-4 border-indigo-500 border-t-transparent rounded-full" />
          <p className="text-sm text-indigo-600 font-medium">
            Parsing PDF with Azure Document Intelligence…
          </p>
        </div>
      ) : fileName ? (
        <div className="flex flex-col items-center gap-2">
          <span className="text-3xl">📄</span>
          <p className="text-sm font-medium text-gray-700">{fileName}</p>
          <label className="cursor-pointer text-xs text-indigo-600 hover:underline">
            Change file
            <input
              type="file"
              accept=".pdf"
              onChange={handleChange}
              className="hidden"
            />
          </label>
        </div>
      ) : (
        <label className="cursor-pointer flex flex-col items-center gap-3">
          <span className="text-4xl">📂</span>
          <p className="text-sm text-gray-500">
            <span className="text-indigo-600 font-medium">Click to upload</span>{" "}
            or drag & drop a PDF
          </p>
          <input
            type="file"
            accept=".pdf"
            onChange={handleChange}
            className="hidden"
          />
        </label>
      )}
    </div>
  );
}

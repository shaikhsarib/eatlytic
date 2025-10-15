
import React, { useRef, useState, useCallback } from 'react';

interface ImageUploaderProps {
  onAnalyze: (file: File) => void;
  isLoading: boolean;
  imagePreview: string | null;
  setImagePreview: (preview: string | null) => void;
}

const CameraIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
);


export const ImageUploader: React.FC<ImageUploaderProps> = ({ onAnalyze, isLoading, imagePreview, setImagePreview }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };
  
  const handleAnalyzeClick = useCallback(() => {
    if (selectedFile) {
        onAnalyze(selectedFile);
    }
  }, [selectedFile, onAnalyze]);

  return (
    <div className="w-full p-6 bg-white rounded-xl shadow-lg border border-gray-200 transition-all duration-300 ease-in-out">
      {!imagePreview ? (
        <div 
          className="flex flex-col items-center justify-center border-2 border-dashed border-gray-300 rounded-lg p-10 cursor-pointer hover:border-green-400 hover:bg-green-50 transition-colors"
          onClick={handleUploadClick}
        >
          <CameraIcon />
          <p className="mt-4 text-lg font-semibold text-gray-600">Snap or Upload a Photo</p>
          <p className="text-sm text-gray-500">Click here to select an image of your food</p>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            accept="image/*"
            capture="environment"
          />
        </div>
      ) : (
        <div className="flex flex-col items-center">
          <img src={imagePreview} alt="Food preview" className="max-h-80 w-auto rounded-lg object-contain mb-6 shadow-md" />
          <button
            onClick={handleAnalyzeClick}
            disabled={isLoading}
            className="w-full md:w-auto px-8 py-3 bg-green-500 text-white font-bold rounded-lg shadow-md hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-opacity-50 transition-all duration-300 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center"
          >
            {isLoading ? (
              <>
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Analyzing...
              </>
            ) : (
              'Analyze Food'
            )}
          </button>
        </div>
      )}
    </div>
  );
};

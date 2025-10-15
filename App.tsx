
import React, { useState, useCallback } from 'react';
import { Header } from './components/Header';
import { ImageUploader } from './components/ImageUploader';
import { AnalysisResult } from './components/AnalysisResult';
import { Loader } from './components/Loader';
import { ErrorDisplay } from './components/ErrorDisplay';
import { FeatureCard } from './components/FeatureCard';
import { FoodAnalysis } from './types';
import { analyzeFoodImage } from './services/geminiService';

const App: React.FC = () => {
  const [analysis, setAnalysis] = useState<FoodAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const handleAnalyze = useCallback(async (file: File) => {
    setIsLoading(true);
    setError(null);
    setAnalysis(null);

    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onloadend = async () => {
      try {
        const base64String = (reader.result as string).split(',')[1];
        if (!base64String) {
          throw new Error("Failed to read image file.");
        }
        const result = await analyzeFoodImage(base64String, file.type);
        setAnalysis(result);
      } catch (e: any) {
        setError(e.message || "An unexpected error occurred.");
      } finally {
        setIsLoading(false);
      }
    };
    reader.onerror = () => {
      setError("Failed to process image file.");
      setIsLoading(false);
    };
  }, []);

  const handleReset = () => {
    setAnalysis(null);
    setError(null);
    setIsLoading(false);
    setImagePreview(null);
  };

  const CameraIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
  );

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#2D3748] font-sans">
      <Header onReset={handleReset} showReset={!!imagePreview} />
      <main className="container mx-auto p-4 md:p-8">
        {!imagePreview && (
          <div className="text-center mb-12">
            <h1 className="text-4xl md:text-5xl font-bold text-[#4A5568] mb-4">Welcome to Eatlytic</h1>
            <p className="text-lg md:text-xl text-gray-600 max-w-2xl mx-auto">Your intelligent food companion for understanding your body's response to food.</p>
          </div>
        )}

        <div className="max-w-4xl mx-auto">
          <ImageUploader 
            onAnalyze={handleAnalyze} 
            isLoading={isLoading} 
            imagePreview={imagePreview}
            setImagePreview={setImagePreview}
            />

          {isLoading && <Loader />}
          {error && <ErrorDisplay message={error} />}
          {analysis && <AnalysisResult data={analysis} />}
          
          {!imagePreview && !analysis && (
            <div className="mt-16">
              <h2 className="text-2xl font-bold text-center text-[#4A5568] mb-8">How Eatlytic Works</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <FeatureCard 
                  icon={<CameraIcon />} 
                  title="Capture" 
                  description="Photograph any food or product label using your phone's camera." 
                />
                <FeatureCard 
                  icon={<svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" /></svg>}
                  title="Analyze" 
                  description="AI instantly identifies the food and extracts detailed nutritional information." 
                />
                <FeatureCard 
                  icon={<svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                  title="Discover Impact" 
                  description="Understand exactly how nutrients affect your body, organs, and overall health." 
                />
              </div>
            </div>
          )}
        </div>
      </main>
      <footer className="text-center p-4 mt-8 text-gray-500">
        <p>&copy; {new Date().getFullYear()} Eatlytic. Making healthy eating effortless.</p>
      </footer>
    </div>
  );
};

export default App;


import React from 'react';
import { FoodAnalysis, BodyImpact, Nutrient } from '../types';

interface AnalysisResultProps {
  data: FoodAnalysis;
}

const IconMap: { [key: string]: React.ReactNode } = {
  Heart: <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>,
  Muscles: <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>,
  Brain: <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>,
  Energy: <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>,
  Digestive: <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547a2 2 0 00-.547 1.806l.477 2.387a6 6 0 00.517 3.86l.158.318a6 6 0 00.517 3.86l2.387.477a2 2 0 001.806-.547a2 2 0 00.547-1.806l-.477-2.387a6 6 0 00-.517-3.86l-.158-.318a6 6 0 00-.517-3.86l-2.387-.477a2 2 0 00-1.022.547zM12 6a2 2 0 100-4 2 2 0 000 4z" /></svg>,
  Default: <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
};


const InfoCard: React.FC<{title: string; children: React.ReactNode; icon?: React.ReactNode}> = ({ title, children, icon }) => (
    <div className="bg-white p-6 rounded-lg shadow-md border border-gray-100">
        <div className="flex items-center mb-3">
            {icon}
            <h3 className="text-xl font-bold text-gray-800 ml-3">{title}</h3>
        </div>
        <div className="text-gray-600">{children}</div>
    </div>
);

const NutrientTable: React.FC<{ nutrients: Nutrient[] }> = ({ nutrients }) => (
    <div className="space-y-2">
        {nutrients.map((nutrient, index) => (
            <div key={index} className="flex justify-between items-baseline">
                <span className="font-medium">{nutrient.name}</span>
                <span className="text-gray-500">{nutrient.amount} {nutrient.unit}</span>
            </div>
        ))}
    </div>
);

export const AnalysisResult: React.FC<AnalysisResultProps> = ({ data }) => {
  return (
    <div className="mt-8 space-y-8 animate-fade-in">
        <div className="text-center p-6 bg-white rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-3xl font-bold text-green-600">{data.recognizedFood}</h2>
            <p className="text-lg text-gray-600 mt-2">{data.summary}</p>
            <div className="mt-4 text-4xl font-extrabold text-gray-800">
                {data.calories}
                <span className="text-xl font-medium text-gray-500 ml-1">kcal</span>
            </div>
        </div>
      
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <InfoCard title="Macro Nutrients">
                <NutrientTable nutrients={data.macros} />
            </InfoCard>
            {data.micros && data.micros.length > 0 && (
                 <InfoCard title="Key Micro Nutrients">
                    <NutrientTable nutrients={data.micros} />
                </InfoCard>
            )}
        </div>

        <InfoCard title="Body Impact Analysis">
            <div className="space-y-4">
            {data.bodyImpacts.map((impact: BodyImpact, index: number) => (
                <div key={index} className="flex items-start">
                    <div className="flex-shrink-0 mt-1">
                        {IconMap[impact.system] || IconMap.Default}
                    </div>
                    <div className="ml-4">
                        <p className="font-bold text-gray-800">{impact.system}</p>
                        <p className="text-gray-600">{impact.description}</p>
                    </div>
                </div>
            ))}
            </div>
        </InfoCard>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
             <InfoCard title="Smart Consumption" icon={<svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>}>
                <p>{data.smartConsumption}</p>
            </InfoCard>
             <InfoCard title="Important Awareness" icon={<svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}>
                <p>{data.importantAwareness}</p>
            </InfoCard>
        </div>
    </div>
  );
};

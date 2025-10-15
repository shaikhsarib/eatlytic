
import React from 'react';

interface FeatureCardProps {
    icon: React.ReactNode;
    title: string;
    description: string;
}

export const FeatureCard: React.FC<FeatureCardProps> = ({ icon, title, description }) => {
    return (
        <div className="bg-white p-6 rounded-lg shadow-md border border-gray-100 text-center transition-transform transform hover:scale-105">
            <div className="flex justify-center items-center text-green-500 mb-4 space-x-2">
                {icon}
                <h3 className="text-xl font-bold text-gray-800">{title}</h3>
            </div>
            <p className="text-gray-600">{description}</p>
        </div>
    );
};

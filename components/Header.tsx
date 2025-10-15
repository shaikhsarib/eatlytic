
import React from 'react';

interface HeaderProps {
    onReset: () => void;
    showReset: boolean;
}

export const Header: React.FC<HeaderProps> = ({ onReset, showReset }) => {
    return (
        <header className="bg-white/80 backdrop-blur-md shadow-sm sticky top-0 z-10">
            <div className="container mx-auto px-4 py-3 flex justify-between items-center">
                <div className="flex items-center space-x-2 cursor-pointer" onClick={onReset}>
                    <svg className="w-8 h-8 text-green-500" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM16.6 13.45C16.6 14.55 15.18 15.45 14.5 15.45C13.82 15.45 13 14.55 13 13.45V12H11V13.45C11 14.55 9.68 15.45 9 15.45C8.32 15.45 7.4 14.55 7.4 13.45L9.2 8.5H14.8L16.6 13.45Z" fill="currentColor"/>
                    </svg>
                    <h1 className="text-2xl font-bold text-gray-800">Eatlytic</h1>
                </div>
                 {showReset && (
                    <button 
                        onClick={onReset}
                        className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
                    >
                        Start Over
                    </button>
                )}
            </div>
        </header>
    );
};

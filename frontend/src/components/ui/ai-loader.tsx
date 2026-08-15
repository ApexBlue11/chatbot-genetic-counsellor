import * as React from "react";

interface LoaderProps {
  size?: number; 
  text?: string;
}

export const Component: React.FC<LoaderProps> = ({ size = 180, text = "Generating" }) => {
  const letters = text.split("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gradient-to-b from-[#1a3379] via-[#0f172a] to-black dark:from-gray-100 dark:via-gray-200 dark:to-gray-300">
      <div
        className="relative flex items-center justify-center font-inter select-none"
        style={{ width: size, height: size }}
      >
        {letters.map((letter, index) => (
          <span
            key={index}
            className="inline-block text-white dark:text-gray-800 opacity-40 animate-loaderLetter"
            style={{ animationDelay: `${index * 0.1}s` }}
          >
            {letter}
          </span>
        ))}

        <div className="absolute inset-0 rounded-full animate-loaderCircle"></div>
      </div>
    </div>
  );
};

export default Component;

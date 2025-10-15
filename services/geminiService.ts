
import { GoogleGenAI, Type } from "@google/genai";
import { FoodAnalysis } from '../types';

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

const analysisSchema = {
  type: Type.OBJECT,
  properties: {
    recognizedFood: { type: Type.STRING, description: "The name of the food item identified in the image." },
    summary: { type: Type.STRING, description: "A brief, one-sentence summary of the food's nutritional profile." },
    calories: { type: Type.NUMBER, description: "Estimated calories for a typical serving size." },
    macros: {
      type: Type.ARRAY,
      description: "List of macronutrients (Protein, Fat, Carbohydrates).",
      items: {
        type: Type.OBJECT,
        properties: {
          name: { type: Type.STRING },
          amount: { type: Type.STRING },
          unit: { type: Type.STRING },
        },
        required: ["name", "amount", "unit"],
      },
    },
    micros: {
        type: Type.ARRAY,
        description: "List of key micronutrients (e.g., vitamins, minerals).",
        items: {
          type: Type.OBJECT,
          properties: {
            name: { type: Type.STRING },
            amount: { type: Type.STRING },
            unit: { type: Type.STRING },
          },
          required: ["name", "amount", "unit"],
        },
    },
    bodyImpacts: {
      type: Type.ARRAY,
      description: "How the food impacts different body systems (Heart, Muscles, Brain, Energy, etc.).",
      items: {
        type: Type.OBJECT,
        properties: {
          system: { type: Type.STRING, description: "The body system affected, e.g., 'Heart', 'Muscles'." },
          description: { type: Type.STRING, description: "Explanation of the impact on that system." },
        },
        required: ["system", "description"],
      },
    },
    smartConsumption: { type: Type.STRING, description: "A practical tip for how to best consume this food, e.g., 'Pair with apple slices for fiber'." },
    importantAwareness: { type: Type.STRING, description: "A key warning or point of awareness, e.g., 'High calorie density; stick to a 2-tablespoon serving'." },
  },
  required: ["recognizedFood", "summary", "calories", "macros", "bodyImpacts", "smartConsumption", "importantAwareness"],
};

export const analyzeFoodImage = async (base64Image: string, mimeType: string): Promise<FoodAnalysis> => {
  try {
    const imagePart = {
      inlineData: {
        data: base64Image,
        mimeType,
      },
    };

    const textPart = {
      text: `Analyze the food in this image. Identify the food, estimate its nutritional information for a standard serving size, and provide a detailed body-impact analysis. Explain how its key nutrients benefit specific organs or body systems (like heart, muscles, brain, digestive system). Also, provide a 'Smart Consumption' tip and an 'Important Awareness' warning. Present the output as a JSON object strictly following the provided schema.`,
    };
    
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: { parts: [imagePart, textPart] },
      config: {
        responseMimeType: "application/json",
        responseSchema: analysisSchema,
      },
    });

    const jsonText = response.text.trim();
    return JSON.parse(jsonText) as FoodAnalysis;

  } catch (error) {
    console.error("Error analyzing food image:", error);
    if (error instanceof Error) {
        throw new Error(`Failed to analyze image with Gemini API: ${error.message}`);
    }
    throw new Error("An unknown error occurred during image analysis.");
  }
};

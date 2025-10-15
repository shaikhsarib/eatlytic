
export interface Nutrient {
  name: string;
  amount: string;
  unit: string;
}

export interface BodyImpact {
  system: string;
  description: string;
}

export interface FoodAnalysis {
  recognizedFood: string;
  summary: string;
  calories: number;
  macros: Nutrient[];
  micros: Nutrient[];
  bodyImpacts: BodyImpact[];
  smartConsumption: string;
  importantAwareness: string;
}

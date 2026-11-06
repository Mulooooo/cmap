export type Routes = number[][];

export interface Config {
  solvers: string[];
  zones: Record<string, { lat: number; lon: number; span: number }>;
  library: string[];
}

/** Instance placée sur la carte (réponse de l'API). */
export interface Inst {
  id: string;
  name: string;
  n: number;
  capacity: number;
  demand: number[];
  total_demand: number;
  min_vehicles: number;
  n_vehicles: number | null;
  bks: number | null;
  has_time_windows: boolean;
  lat: number[];
  lon: number[];
  km_per_unit: number;
  zone: string;
  span: number;
}

export interface RouteStat {
  load: number;
  dist: number;
  n: number;
}

export interface Solution {
  solver: string;
  routes: Routes;
  cost: number;
  gap: number | null;
  valid: boolean;
  errors: string[];
  elapsed: number;
  history: [number, number, number][]; // [temps_s, itération, meilleur coût]
  per_route: RouteStat[];
}

export interface Progress {
  it: number;
  cost: number;
  elapsed: number;
  routes: Routes;
}

export type Basemap = "light" | "dark";

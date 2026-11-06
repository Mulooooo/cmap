import type { Config, Inst, Progress, Solution } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* corps non JSON */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

const placement = (zone: string, span: number) =>
  new URLSearchParams({ zone, span: String(span) });

export const getConfig = () => request<Config>("/api/config");

export const loadLibrary = (name: string, zone: string, span: number) =>
  request<Inst>(`/api/instances/library/${encodeURIComponent(name)}?${placement(zone, span)}`, {
    method: "POST",
  });

export const uploadInstance = (file: File, zone: string, span: number) => {
  const q = placement(zone, span);
  q.set("filename", file.name);
  return request<Inst>(`/api/instances?${q}`, { method: "POST", body: file });
};

export const replaceInstance = (id: string, zone: string, span: number) =>
  request<Inst>(`/api/instances/${id}?${placement(zone, span)}`);

export interface SolveOptions {
  instance: string;
  solver: string;
  timeLimit: number;
  seed: number;
}

export interface SolveHandlers {
  onProgress(p: Progress): void;
  onDone(s: Solution): void;
  onError(message: string): void;
}

/** Lance un calcul (flux SSE). Renvoie une fonction qui l'interrompt. */
export function solve(opts: SolveOptions, h: SolveHandlers): () => void {
  const q = new URLSearchParams({
    instance: opts.instance,
    solver: opts.solver,
    time_limit: String(opts.timeLimit),
    seed: String(opts.seed),
  });
  const es = new EventSource(`/api/solve?${q}`);
  let finished = false;
  const stop = () => {
    finished = true;
    es.close();
  };

  es.addEventListener("progress", (e) => h.onProgress(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("done", (e) => {
    stop();
    h.onDone(JSON.parse((e as MessageEvent).data));
  });
  // "error" est aussi l'événement envoyé par le serveur quand le solveur plante (avec des données)
  es.addEventListener("error", (e) => {
    if (finished) return;
    const data = (e as MessageEvent).data;
    stop();
    h.onError(data ? `Erreur du solveur : ${JSON.parse(data).message}` : "Connexion au serveur perdue.");
  });
  return stop;
}

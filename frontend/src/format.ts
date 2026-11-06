export const PALETTE = [
  "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf",
  "#bcbd22", "#7f7f7f", "#393b79", "#e6550d", "#31a354", "#756bb1", "#843c39", "#d6616b",
  "#637939", "#8ca252", "#3182bd", "#fd8d3c",
];
export const IDLE_COLOR = "#4a6fa5";
export const routeColor = (i: number) => PALETTE[i % PALETTE.length];

const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
export const fmt = (x: number) => nf.format(x);

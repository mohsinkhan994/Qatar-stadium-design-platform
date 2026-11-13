const ICONS = {
  football: '<circle cx="12" cy="12" r="8.5"/><path d="m12 7 3 2.2-1.15 3.55h-3.7L9 9.2 12 7Zm-3 2.2-2.3-.2m8.3.2 2.4-.2m-6 4.55-.9 3m3.6-3-.9 3m-6.5-2-2.2 1m14.4-1 2.2 1"/>',
  capacity: '<ellipse cx="12" cy="13" rx="9" ry="5.5"/><ellipse cx="12" cy="13" rx="5.8" ry="2.8"/><path d="M3 13v3m18-3v3M6 16v2m12-2v2"/>',
  setting: '<path d="M4 19h16M5 19l7-14 7 14M8.5 12h7M7 16h10"/>',
  theme: '<path d="M4 18c3-8 13-12 16-9-1 4-6 11-13 10m2-2 7-6"/><circle cx="17.5" cy="6.5" r="1.5"/>',
  style: '<path d="M5 19h14M7 19V9l5-4 5 4v10M9.5 19v-5h5v5M5 9h14"/>',
  shape: '<ellipse cx="12" cy="12" rx="9" ry="5.5"/><ellipse cx="12" cy="12" rx="5.8" ry="2.8"/>',
  roof: '<path d="M3 16c2-8 14-11 18 0M4 16h16M7 16v2m5-2v2m5-2v2"/>',
  materials: '<path d="M4 8 12 4l8 4-8 4-8-4Zm0 4 8 4 8-4m-16 4 8 4 8-4"/>',
  palette: '<circle cx="12" cy="12" r="9"/><path d="M12 3v9h9M6 6l6 6m-8 0h8m0 0 4 7"/>',
  experience: '<path d="M3 18h18M5 17v-5l7-5 7 5v5M9 17v-4h6v4m-3-10V4"/>',
  innovation: '<path d="M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8m-7.2 7.2-2.8 2.8"/><circle cx="12" cy="12" r="3.5"/>',
  technologies: '<path d="M12 3 4.5 7v6c0 4 3.2 6.6 7.5 8 4.3-1.4 7.5-4 7.5-8V7L12 3Zm-3.5 9 2.3 2.3 4.8-5"/>',
  environment: '<path d="M19.5 4.5c-8 .2-14 2.7-14 8.2a5.3 5.3 0 0 0 5.2 5.3c5.8 0 8.1-6.7 8.8-13.5ZM4 21c2.2-5.4 5.8-8.9 11.4-12"/>',
  legacy: '<path d="M4 19h16M6 19V8l6-4 6 4v11M9 19v-6h6v6M4 9h16"/>',
  signature: '<path d="M4 17.5 16.5 5l2.5 2.5L6.5 20H4v-2.5ZM13.5 8l2.5 2.5M4 22h16"/>',
  fallback: '<circle cx="12" cy="12" r="8"/><path d="m8 12 2.5 2.5L16 9"/>',
};

export function icon(key) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[key] || ICONS.fallback}</svg>`;
}


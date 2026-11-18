import React from 'react';

export function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    overview: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
    interviews: 'M4 5h16v12H8l-4 4V5zM8 9h8M8 13h5',
    questions: 'M4 4h7v16H4zM11 4h9v16h-9M7 8h1M14 8h3M14 12h3',
    accounts:
      'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8M18 4a4 4 0 0 1 0 8M22 21v-3a4 4 0 0 0-3-3.8',
    refresh: 'M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 13-2l2 2M4 17l2 2a8 8 0 0 0 13-2',
    menu: 'M4 6h16M4 12h16M4 18h16',
    arrow: 'M9 5l7 7-7 7',
    audit: 'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',
  };
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.overview} />
    </svg>
  );
}

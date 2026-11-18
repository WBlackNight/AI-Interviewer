import React from 'react';
import { createRoot } from 'react-dom/client';
import { ErrorBoundary } from '../shared/ErrorBoundary';
import { WidgetApp } from './WidgetApp';
const root = document.getElementById('qing-widget-root');
if (root)
  createRoot(root).render(
    <ErrorBoundary>
      <WidgetApp />
    </ErrorBoundary>
  );

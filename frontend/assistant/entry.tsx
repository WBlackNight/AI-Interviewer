import React from 'react';
import { createRoot } from 'react-dom/client';
import { AssistantApp } from './AssistantApp';
import { ErrorBoundary } from '../shared/ErrorBoundary';

const root = document.getElementById('assistant-root');
if (root)
  createRoot(root).render(
    <ErrorBoundary>
      <AssistantApp />
    </ErrorBoundary>
  );

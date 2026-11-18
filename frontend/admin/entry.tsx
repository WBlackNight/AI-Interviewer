import React from 'react';
import { createRoot } from 'react-dom/client';
import { ErrorBoundary } from '../shared/ErrorBoundary';
import { AdminApp } from './AdminApp';
const root = document.getElementById('admin-root');
if (root)
  createRoot(root).render(
    <ErrorBoundary>
      <AdminApp />
    </ErrorBoundary>
  );

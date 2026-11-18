import React from 'react';
import { createRoot } from 'react-dom/client';
import { StudioApp } from './StudioApp';
import { ErrorBoundary } from '../shared/ErrorBoundary';

const root = document.getElementById('practice-root');
const id = location.pathname.match(/^\/interview\/([a-f0-9]{32})$/)?.[1];
if (root)
  createRoot(root).render(
    <ErrorBoundary>
      {id ? (
        <StudioApp interviewId={id} />
      ) : (
        <div className="practice-card">
          <h1>请选择一场练习</h1>
          <p>从首页设置方向与时长，开始你的下一次准备。</p>
          <a href="/#start">开始练习</a>
        </div>
      )}
    </ErrorBoundary>
  );

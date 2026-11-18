/* 青栈首页：原生DOM，无依赖。 */
(function () {
  'use strict';
/* @include notice */
/* @include session */
/* @include fetch */
/* @include http */
/* @include practiceintent */
/* @include practicepreview */

  const select = (selector) => document.querySelector(selector);
  const selectAll = (selector) => Array.from(document.querySelectorAll(selector));
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const compactHome = matchMedia('(max-width: 700px), (max-width: 950px) and (pointer: coarse)');
  const catalog = /* @practice-catalog */;

/* @module home/navigation */
/* @module home/input */
/* @module home/demonstration */
/* @module home/motion */
/* @module home/evidence */
/* @module home/practice */
/* @module home/carousel */

  // 初始化：模块独立启用，局部失败不影响其他功能。
  [deviceHome, mobileHome, navigation, heroDemo, homepageCounts, questionDemo, revealSections, scoringEvidence, practiceForm, resumeInput, practicePreview, workspaceLinks, accountCarousel].forEach((initialize) => {
    try { initialize(); }
    catch { document.documentElement.classList.add('partial-interaction'); }
  });
})();

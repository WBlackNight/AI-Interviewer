/* Compatibility command; current React entries are built with Vite. */
import('./build_frontend.mjs').catch(() => {console.error('Run npm ci in frontend, then npm run build.'); process.exitCode = 1;});

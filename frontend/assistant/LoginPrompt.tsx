import React from 'react';

export function LoginPrompt({ returnTo, fullPage }: { returnTo: string; fullPage?: boolean }) {
  return (
    <section className="qing-auth-prompt" aria-labelledby="qing-login-heading">
      {fullPage && <h1>小青助手</h1>}
      <h2 id="qing-login-heading">登录后才能使用小青助手</h2>
      <p>登录后可以向小青提问，并在账户中回看对话。</p>
      <a
        className="notes-button notes-primary"
        href={'/account?next=' + encodeURIComponent(returnTo)}
      >
        前往登录
      </a>
    </section>
  );
}

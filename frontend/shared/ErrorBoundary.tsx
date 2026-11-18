import React from 'react';

export class ErrorBoundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <section role="alert" className="notes-message">
        <h1>页面暂时遇到问题</h1>
        <p>已保存的数据可在重新打开后查看。</p>
        <button type="button" onClick={() => location.reload()}>
          重新加载
        </button>
        <a href="/">回到首页</a>
      </section>
    ) : (
      this.props.children
    );
  }
}

import { useEffect, useLayoutEffect, useState } from 'react';
import { getAccountSession } from '../lib/account';
import { adminRequest, AdminError, Overview, Page } from './api';
import { Route, listPath } from './state';
export function useAdmin(route: Route) {
  const [identity, setIdentity] = useState(() => getAccountSession()?.access_token || '');
  const [version, setVersion] = useState(0);
  const [data, setData] = useState<{ overview: Overview; page: Page } | null>(null);
  const [error, setError] = useState<AdminError | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const changed = () => {
      setData(null);
      setError(null);
      setIdentity(getAccountSession()?.access_token || '');
      setVersion((v) => v + 1);
    };
    addEventListener('account:changed', changed);
    addEventListener('account:expired', changed);
    const restore = (e: PageTransitionEvent) => {
      if (e.persisted) changed();
    };
    addEventListener('pageshow', restore);
    return () => {
      removeEventListener('account:changed', changed);
      removeEventListener('account:expired', changed);
      removeEventListener('pageshow', restore);
    };
  }, []);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const check = () => {
      const session = getAccountSession();
      if (!session || session.access_token !== identity) {
        setData(null);
        setError(null);
        setIdentity('');
        return;
      }
      clearTimeout(timer);
      timer = setTimeout(
        check,
        Math.min(2147483647, Math.max(1, Date.parse(session.expires_at) - Date.now()))
      );
    };
    check();
    addEventListener('focus', check);
    document.addEventListener('visibilitychange', check);
    return () => {
      clearTimeout(timer);
      removeEventListener('focus', check);
      document.removeEventListener('visibilitychange', check);
    };
  }, [identity, version]);
  useLayoutEffect(() => {
    setData(null);
    setError(null);
    if (!identity) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    Promise.all([
      adminRequest<Overview>('/api/admin/overview?days=' + route.days, identity, controller.signal),
      adminRequest<Page>(listPath(route), identity, controller.signal),
    ])
      .then(([overview, page]) => {
        if (active) setData({ overview, page });
      })
      .catch((error) => {
        if (active)
          setError(error instanceof AdminError ? error : new AdminError('读取失败，请稍后重试。'));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [identity, version, route]);
  return { identity, data, error, loading, refresh: () => setVersion((v) => v + 1) };
}

export type Evidence = {
  sources: { id: string; title: string; theme?: string; content?: string; href: string }[];
  actions: { label: string; href: string }[];
  workflow?: string;
};
export type Message = {
  role: 'user' | 'assistant';
  content: string;
  evidence?: Evidence;
  mode?: { value: string; label: string };
  request_id?: string;
};
export type Conversation = {
  id: string;
  title: string;
  position: string;
  version: number;
  messages: Message[];
};
export type Role = { name: string; group: string; themes: string[] };
export type Session = {
  access_token: string;
  account: { id: string; username: string };
  expires_at: string;
};
export type ChatEvent =
  | { type: 'stage'; label: string }
  | ({ type: 'evidence' } & Evidence)
  | { type: 'delta'; text: string }
  | { type: 'revision'; text: string; reason: string }
  | { type: 'mode'; value: string; label: string }
  | { type: 'done'; version: number }
  | { type: 'error'; message: string };

export function session(): Session | null {
  try {
    const value = JSON.parse(sessionStorage.getItem('account:session') || 'null');
    return value &&
      /^[a-f0-9]{64}$/.test(value.access_token) &&
      /^[a-f0-9]{32}$/.test(value.account?.id) &&
      Date.parse(value.expires_at) > Date.now()
      ? value
      : null;
  } catch {
    return null;
  }
}

export function notice(message: string, type = 'success') {
  dispatchEvent(new CustomEvent('app:notice', { detail: { message, type } }));
}

// The server supplies links, but the client also restricts them to known same-origin paths.
export function safeLink(href: string) {
  return /^\/(?:\?(?:[^#]*)#start|catalog\?|guide$|report\/[a-f0-9]{32}$)/.test(href) &&
    !href.includes('\\')
    ? href
    : '/guide';
}

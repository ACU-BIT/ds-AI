
// كل استدعاءات الـ API هنا
const BASE = '';

const token = () => localStorage.getItem('td_token');

async function api(path, opts = {}) {
  const isForm = opts.body instanceof FormData;

  const r = await fetch(BASE + '/api' + path, {
    ...opts,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(token() ? { Authorization: 'Bearer ' + token() } : {}),
      ...opts.headers
    },
    body: opts.body && !isForm && typeof opts.body !== 'string'
      ? JSON.stringify(opts.body)
      : opts.body
  });

  if (r.status === 401) {
    localStorage.removeItem('td_token');
    location.href = 'login.html';
    throw new Error('انتهت جلسة تسجيل الدخول');
  }

  const data = await r.json().catch(() => ({}));

  if (!r.ok) {
    throw new Error(data.detail || 'حصل خطأ، جرّب تاني');
  }

  return data;
}

const API = {
  signup: (d) => api('/auth/register', { method: 'POST', body: d }),
  login: (d) => api('/auth/login', { method: 'POST', body: d }),
  demo: () => api('/auth/demo', { method: 'POST' }),
  me: () => api('/auth/me'),

  documents: () => api('/documents'),

  upload: (file) => {
    const f = new FormData();
    f.append('file', file);
    return api('/documents/upload', { method: 'POST', body: f });
  },

  addText: (d) => api('/documents/text', { method: 'POST', body: d }),
  deleteDoc: (id) => api('/documents/' + id, { method: 'DELETE' }),

  connectBot: (tk) => api('/bots/connect', {
    method: 'POST',
    body: { token: tk }
  }),

  testBot: (d) => api('/bots/test', { method: 'POST', body: d }),
  bot: () => api('/bots'),
  toggleBot: () => api('/bots/toggle', {
  method: 'POST'
}),

disconnectBot: () => api('/bots/disconnect', {
  method: 'POST'
}),
  conversations: () => api('/conversations'),
  company: () => api('/company'),
  saveCompany: (d) => api('/company', { method: 'PUT', body: d })
};

async function authForm(e, kind) {
  e.preventDefault();

  const d = Object.fromEntries(new FormData(e.target));
  const errorElement = document.getElementById('err');

  if (errorElement) errorElement.textContent = '';

  try {
    const r = await API[kind](d);

    if (!r || !r.token) {
      throw new Error('السيرفر لم يرجع رمز تسجيل الدخول');
    }

    localStorage.setItem('td_token', r.token);
    location.href = 'dashboard.html';

  } catch (err) {
    if (errorElement) {
      errorElement.textContent = err.message || 'فشل تسجيل الدخول';
    } else {
      alert(err.message || 'فشل تسجيل الدخول');
    }
  }
}

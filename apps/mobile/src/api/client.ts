import Constants from 'expo-constants';
import { secureStorage } from './secure-storage';

/**
 * Single place every network call goes through.
 *
 * Security posture: the APK is assumed to be readable by anyone. Nothing here
 * decides what a user is allowed to do — the server re-checks eligibility,
 * verification state and fraud limits on every request. The app only decides
 * what to *draw*. Treat every field returned here as display data.
 */

/**
 * Where the API lives.
 *
 * `EXPO_PUBLIC_API_BASE_URL` wins so one checkout can be built for dev,
 * staging and production without editing app.json — Expo inlines any
 * `EXPO_PUBLIC_*` variable at build time, and the web and Android builds read
 * the same one. Falls back to app.json, then to the Android emulator's alias
 * for the host machine.
 */
const API_BASE_URL: string =
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  (Constants.expoConfig?.extra as { apiBaseUrl?: string } | undefined)?.apiBaseUrl ??
  'http://10.0.2.2:3001/api/v1';

const CSRF_KEY = 'bbazaar.csrfToken';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** The session is gone or was never there — send the user to sign in. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** Authenticated, but not allowed yet (unverified, not eligible, suspended). */
  get isForbidden(): boolean {
    return this.status === 403;
  }
}

async function getCsrfToken(): Promise<string | null> {
  return secureStorage.get(CSRF_KEY);
}

async function setCsrfToken(token: string | null): Promise<void> {
  return secureStorage.set(CSRF_KEY, token);
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Set false for calls that must not trigger a refresh-and-retry loop. */
  allowRefresh?: boolean;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, allowRefresh = true } = options;

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  // The server requires this header on every state-changing request.
  if (method !== 'GET') {
    const csrf = await getCsrfToken();
    if (csrf) headers['x-csrf-token'] = csrf;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    // Session cookies are set by the server and held by the platform cookie
    // jar; no token is ever stored in JS.
    credentials: 'include',
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && allowRefresh) {
    // One silent refresh, then replay. `allowRefresh: false` on the retry
    // stops this recursing if the refresh itself 401s.
    const refreshed = await tryRefresh();
    if (refreshed) return request<T>(path, { ...options, allowRefresh: false });
  }

  const text = await response.text();
  const payload = text ? safeJsonParse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, extractMessage(payload) ?? response.statusText, payload);
  }

  return payload as T;
}

async function tryRefresh(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return false;
    const body = safeJsonParse(await response.text()) as { csrfToken?: string } | null;
    if (body?.csrfToken) await setCsrfToken(body.csrfToken);
    return true;
  } catch {
    return false;
  }
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Nest's exception filter nests the real message one level down. */
function extractMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null;
  const outer = payload as { message?: unknown };
  const inner = outer.message;
  if (typeof inner === 'string') return inner;
  if (inner && typeof inner === 'object') {
    const m = (inner as { message?: unknown }).message;
    if (typeof m === 'string') return m;
    if (Array.isArray(m)) return m.join('\n');
  }
  return null;
}

// ---------------------------------------------------------------------------
// Response shapes, mirroring the NestJS controllers.
// ---------------------------------------------------------------------------

export type Vacancy = {
  id: string;
  title: string;
  state: string;
  tier: string;
  postCount: number;
  salaryMonthlyRupees: number;
  status: string;
};

export type Me = {
  id: string;
  mobile: string;
  status: string;
  role: string;
  referralCode: string;
  createdAt: string;
};

export type ReferralStats = {
  ceiling: number;
  total: number;
  verified: number;
  rejected: number;
  pending: number;
  remaining: number;
  ceilingReached: boolean;
  fraud: { strikes: number; limit: number; remainingBeforeSuspension: number };
};

export type ReferralSummary = {
  referralCode: string;
  referrals: Array<{
    id: string;
    status: string;
    createdAt: string;
    creditedAt: string | null;
    rejectionReasonCode: string | null;
  }>;
  progress: {
    referrals: { completed: number; required: number };
    kycChallenges: { completed: number; required: number };
  };
  stats: ReferralStats;
};

export type TelegramState = {
  botStarted: boolean;
  contactVerified: boolean;
  joinedPublicChat: boolean;
  joinedPrivateChat: boolean;
  complete: boolean;
  userStatus: string | null;
};

export type TelegramLinkInfo = {
  botLink: string;
  botUsername: string;
  publicChatInviteLink: string | null;
  privateChatInviteLink: string | null;
  connected: boolean;
  contactVerified: boolean;
};

export type Challenge = {
  attemptId: string;
  /** The number to read, grouped 4-4-4 as it appears on a card. */
  numberDisplay: string;
  /** What to answer about it. */
  question: string;
  /** What a correct answer looks like, e.g. "4 digits". */
  answerHint: string;
  expiresAt: string;
};

export type ChallengeResult = {
  attemptId: string;
  correct: boolean;
  /** Revealed only after submitting, so a miss is something to learn from. */
  correctAnswer: string;
  promotedToApplicationEligible: boolean;
};

export type SelectionStatus = {
  qualified: boolean;
  status: string | null;
  progress: ReferralSummary['progress'];
};

export const api = {
  // Public
  vacancies: () => request<{ vacancies: Vacancy[] }>('/vacancies'),

  // Auth
  signup: (input: {
    aadhaarNumber: string;
    mobile: string;
    password: string;
    confirmPassword: string;
    referralCode?: string;
    consentAccepted: boolean;
    captchaToken: string;
  }) =>
    request<{ userId: string; status: string; referralCode: string }>('/auth/signup', {
      method: 'POST',
      body: input,
      allowRefresh: false,
    }),

  login: async (input: { mobile: string; password: string; captchaToken: string }) => {
    const result = await request<{ user: { id: string; role: string }; csrfToken: string }>(
      '/auth/login',
      { method: 'POST', body: input, allowRefresh: false },
    );
    await setCsrfToken(result.csrfToken);
    return result;
  },

  logout: async () => {
    try {
      await request<{ ok: boolean }>('/auth/logout', { method: 'POST', allowRefresh: false });
    } finally {
      // Clear locally even if the server call failed, so the app never looks
      // signed in with a session it cannot use.
      await setCsrfToken(null);
    }
  },

  me: () => request<Me>('/users/me'),

  // Telegram verification
  telegramLink: () => request<TelegramLinkInfo>('/telegram/link'),
  telegramState: () => request<TelegramState>('/telegram/state'),
  telegramRecheck: () => request<TelegramState>('/telegram/recheck', { method: 'POST' }),

  // Referrals
  referrals: () => request<ReferralSummary>('/referrals/me'),

  // KYC training
  nextChallenge: () => request<Challenge>('/kyc-training/next-challenge'),
  submitChallenge: (attemptId: string, answer: string) =>
    request<ChallengeResult>(`/kyc-training/attempts/${attemptId}/submit`, {
      method: 'POST',
      body: { answer },
    }),

  // Applications
  apply: (input: { statePreference: string; tierPreference: string; districtPreference?: string }) =>
    request<{ id: string; status: string }>('/applications', { method: 'POST', body: input }),
  myApplication: () => request<{ id: string; status: string } | null>('/applications/me'),

  // Selection
  selectionStatus: () => request<SelectionStatus>('/selection/status'),
  groupInvite: () => request<{ inviteLink: string }>('/selection/group-invite'),
};

export { API_BASE_URL };

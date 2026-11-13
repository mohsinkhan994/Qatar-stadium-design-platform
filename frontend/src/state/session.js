export const STORAGE_KEY = 'qma-stadium-session-v1';

export const state = {
  phase: 'boot', health: null, questionnaire: null, session: null,
  revision: 0, answers: {}, questionIndex: 0, review: null, job: null,
  notice: '', error: '', requestPending: false, pollTimer: null,
};


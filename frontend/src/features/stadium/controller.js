import { request } from '../../api/client.js';
import { state, STORAGE_KEY } from '../../state/session.js';
import { render, canContinue } from './views.js';

const app = document.querySelector('#app');
const announcer = document.querySelector('#announcer');

function setError(error) {
  state.error = error instanceof Error ? error.message : String(error);
  render();
  window.setTimeout(() => { state.error = ''; render(); }, 6500);
}

function saveLocal() {
  if (!state.session) return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify({id:state.session.id, phase:state.phase, questionIndex:state.questionIndex}));
}

async function beginSession() {
  state.requestPending = true; state.error = ''; render();
  try {
    state.session = await request('/api/v1/sessions', {method:'POST', body:JSON.stringify({language:'en'})});
    state.answers = {}; state.revision = state.session.revision; state.questionIndex = 0;
    state.notice = ''; state.phase = 'question'; saveLocal(); render();
    focusQuestion();
  } catch (error) { state.phase = 'home'; setError(error); }
  finally {
    state.requestPending = false;
    if (state.phase === 'home') render();
  }
}

function focusQuestion() {
  requestAnimationFrame(() => app.querySelector('.question-head h2')?.focus?.());
}

async function persistAnswer(question, value) {
  if (state.requestPending) return false;
  state.requestPending = true;
  try {
    const updated = await request(`/api/v1/sessions/${state.session.id}/answers`, {
      method:'PATCH', body:JSON.stringify({revision:state.revision, answers:{[question.id]:value}}),
    });
    state.answers = updated.answers; state.revision = updated.revision; saveLocal(); return true;
  } catch (error) { setError(error); return false; }
  finally { state.requestPending = false; }
}

async function goReview() {
  state.requestPending = true; state.error = ''; render();
  try {
    state.review = await request(`/api/v1/sessions/${state.session.id}/review`);
    state.phase = 'review'; saveLocal(); render();
  } catch (error) { state.phase = 'question'; setError(error); }
  finally {
    state.requestPending = false;
    if (state.phase === 'review') render();
  }
}

function confirmedNotes(review) {
  const notes = review.notes_to_confirm || [];
  if (!notes.length) return [];
  const list = notes.map(n => `• ${n.message}`).join('\n');
  return window.confirm(`A design note helps us show your choices clearly:\n\n${list}\n\nContinue with these notes while keeping your selections?`)
    ? notes.map(n=>n.code) : null;
}

async function startGeneration() {
  if (state.requestPending) return;
  state.requestPending = true; state.error = ''; render();
  try {
    state.review = await request(`/api/v1/sessions/${state.session.id}/review`);
    const acceptedNotes = confirmedNotes(state.review);
    if (acceptedNotes === null) { state.requestPending = false; state.phase='review'; render(); return; }
    const key = `qma-stadium-request-${state.session.id}`;
    let requestId = localStorage.getItem(key);
    if (!requestId) { requestId = crypto.randomUUID(); localStorage.setItem(key, requestId); }
    const job = await request(`/api/v1/sessions/${state.session.id}/generations`, {
      method:'POST', body:JSON.stringify({request_id:requestId, revision:state.revision, accepted_notes:acceptedNotes}),
    });
    state.job = job; localStorage.setItem(`qma-stadium-job-${state.session.id}`,job.id);
    state.phase = job.status === 'completed' ? 'result' : ['failed','interrupted','cancelled'].includes(job.status) ? 'error' : 'generating'; saveLocal(); render();
    if (state.phase === 'generating') pollJob(job.id);
  } catch (error) { state.phase='review'; setError(error); }
  finally {
    state.requestPending = false;
    if (state.phase === 'review') render();
  }
}

function pollJob(jobId) {
  clearTimeout(state.pollTimer);
  const tick = async () => {
    try {
      const job = await request(`/api/v1/generations/${jobId}`);
      state.job = job;
      if (job.status === 'completed') state.phase = 'result';
      else if (['failed','interrupted','cancelled'].includes(job.status)) state.phase = 'error';
      else { render(); state.pollTimer=window.setTimeout(tick,1300); return; }
      saveLocal(); render();
      announcer.textContent = state.phase === 'result' ? 'Your stadium design is ready.' : 'Image generation paused.';
    } catch (error) {
      state.error = error.message; render(); state.pollTimer=window.setTimeout(tick,2500);
    }
  };
  state.pollTimer = window.setTimeout(tick,800);
}

async function retryGeneration() {
  const key = `qma-stadium-request-${state.session.id}`;
  localStorage.removeItem(key);
  state.phase = 'review'; state.error = ''; render();
  await startGeneration();
}

async function finishExperience() {
  state.requestPending = true; render();
  try {
    const result = await request(`/api/v1/sessions/${state.session.id}/finish`, {method:'POST'});
    clearTimeout(state.pollTimer);
    const reference = result.archive_reference;
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(`qma-stadium-job-${state.session.id}`);
    localStorage.removeItem(`qma-stadium-request-${state.session.id}`);
    state.session=null; state.answers={}; state.job=null; state.review=null; state.revision=0;
    state.questionIndex=0; state.notice=`Your stadium has been saved. Archive reference: ${reference}`;
    state.phase='home'; render();
  } catch (error) { setError(error); }
  finally { state.requestPending = false; }
}

async function resume() {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
  if (!saved?.id) return;
  try {
    const session = await request(`/api/v1/sessions/${saved.id}`);
    state.session=session; state.answers=session.answers; state.revision=session.revision;
    state.questionIndex=Math.min(Number(saved.questionIndex)||0,state.questionnaire.questions.length-1);
    const active = session.generations.find(job=>['queued','generating','validating','retrying','saving'].includes(job.status));
    const latest = session.generations[0];
    if (active) { state.job=active; state.phase='generating'; pollJob(active.id); }
    else if (latest?.status === 'completed') { state.job=latest; state.phase='result'; }
    else if (latest && ['failed','interrupted','cancelled'].includes(latest.status)) { state.job=latest; state.phase='error'; }
    else if (saved.phase === 'review') { state.phase='review'; }
    else { state.phase='question'; }
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    state.phase='home'; state.notice='Your previous session is no longer available. You can start a new design.';
  }
}

app.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  if (action === 'start') return beginSession();
  if (action === 'choose') {
    const question = state.questionnaire.questions.find(q=>q.id===button.dataset.question);
    if (!question) return;
    const id=button.dataset.option;
    if (question.type === 'multiple') {
      const selected=new Set(state.answers[question.id] || []);
      if (selected.has(id)) selected.delete(id);
      else if (selected.size < question.max_selections) selected.add(id);
      state.answers[question.id]=[...selected];
    } else {
      state.answers[question.id]= question.id==='signature' ? {mode:'surprise'} : id;
    }
    render();
    const focusTarget=[...app.querySelectorAll('[data-action="choose"]')].find(el=>el.dataset.question===question.id&&el.dataset.option===id);
    focusTarget?.focus();
    return;
  }
  if (action === 'continue') {
    const question=state.questionnaire.questions[state.questionIndex];
    if (!canContinue(question)) return;
    const value=state.answers[question.id];
    if (!await persistAnswer(question,value)) return;
    if (state.questionIndex < state.questionnaire.questions.length-1) {
      state.questionIndex++; saveLocal(); render(); focusQuestion();
    } else await goReview();
    return;
  }
  if (action === 'back') {
    if (state.questionIndex === 0) {
      if (window.confirm('Leave this design? Your saved answers will be available if you return on this device.')) {
        state.phase='home'; render();
      }
    } else {
      state.questionIndex--; saveLocal(); render(); focusQuestion();
    }
    return;
  }
  if (action === 'review') return goReview();
  if (action === 'edit') {
    state.phase='question'; state.questionIndex=0; saveLocal(); render(); return;
  }
  if (action === 'generate') return startGeneration();
  if (action === 'retry') return retryGeneration();
  if (action === 'finish') return finishExperience();
});

app.addEventListener('input', event => {
  if (event.target.id !== 'signature-input') return;
  const text=event.target.value.slice(0,140);
  event.target.value=text;
  state.answers.signature={mode:'text',text};
  const count=app.querySelector('#signature-count');
  if (count) count.textContent=`${text.length} / 140`;
  const next=app.querySelector('[data-action="continue"]');
  if (next) next.disabled=!text.trim();
});

window.addEventListener('online', async () => {
  try { state.health=await request('/health'); state.error=''; render(); } catch { /* Banner will be set by the next action. */ }
});

export async function boot() {
  render();
  try {
    [state.health,state.questionnaire]=await Promise.all([request('/health'),request('/api/v1/questionnaire')]);
    await resume();
    render();
    if (!state.session) state.phase='home';
    render();
  } catch (error) {
    state.phase='home'; state.error=`The design service is not ready. ${error.message}`; render();
  }
}


import { state } from '../../state/session.js';
import { icon } from '../../components/icons.js';
import { escapeHtml } from '../../lib/html.js';

const app = document.querySelector('#app');

function art() {
  return `<svg viewBox="0 0 640 600" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Illustration of a sculptural stadium in a green landscape">
    <defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="#dce7e0"/><stop offset="1" stop-color="#e9e4d8"/></linearGradient><linearGradient id="bowl" x2=".2" y2="1"><stop stop-color="#e4d8c1"/><stop offset="1" stop-color="#aa9778"/></linearGradient><filter id="shadow"><feGaussianBlur stdDeviation="17"/></filter></defs>
    <rect width="640" height="600" fill="url(#sky)"/>
    <circle cx="510" cy="116" r="46" fill="#ead4a9" opacity=".75"/>
    <path d="M0 388Q150 287 300 364t340-12v248H0Z" fill="#a7bbaa"/><path d="M0 455q154-100 327-13t313-5v163H0Z" fill="#879d8a"/>
    <ellipse cx="331" cy="465" rx="226" ry="39" fill="#385b4b" opacity=".22" filter="url(#shadow)"/>
    <path d="M132 337Q152 228 332 205q173 19 190 132v103q-25 110-192 114-169-3-198-117Z" fill="url(#bowl)" stroke="#657b6b" stroke-width="4"/>
    <ellipse cx="331" cy="338" rx="199" ry="103" fill="#d8c8a9" stroke="#536e5d" stroke-width="5"/>
    <ellipse cx="331" cy="338" rx="151" ry="72" fill="#f0e9d9" stroke="#9a8d76" stroke-width="2"/>
    <ellipse cx="331" cy="343" rx="108" ry="47" fill="#789376"/>
    <path d="M231 343h200M331 296v94" stroke="#f7f2e7" stroke-width="2"/><circle cx="331" cy="343" r="17" fill="none" stroke="#f7f2e7" stroke-width="2"/>
    <path d="M132 337q26-106 200-132 169 19 190 132" fill="none" stroke="#fff9ec" stroke-width="12" stroke-linecap="round"/>
    <path d="M154 314q-20-75 67-105M510 314q20-75-67-105" fill="none" stroke="#b88b52" stroke-width="4"/>
    <path d="M101 483q135 55 260 39t199-45" fill="none" stroke="#e5dfcf" stroke-width="12" stroke-linecap="round"/>
    <path d="M122 503q22 20 42 0m-18 13q17 17 36 2m352-28q-16 17-32 5" stroke="#e7e3d9" stroke-width="4" fill="none"/>
    <g fill="#4d7458"><circle cx="97" cy="405" r="12"/><circle cx="78" cy="409" r="9"/><circle cx="574" cy="415" r="14"/><circle cx="596" cy="421" r="10"/></g>
  </svg><div class="hero-caption"><span>Architecture for everyone</span><span>01 / 15</span></div>`;
}

function shell(content) {
  const mock = state.health?.is_mock ?? state.health?.provider === 'mock';
  return `<header class="topbar">
    <div class="brand"><svg class="brand-mark" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M4 26c0-9 7-16 16-16s16 7 16 16v5H4v-5Z" fill="currentColor"/><ellipse cx="20" cy="25" rx="10" ry="5" stroke="#f5f3ee" stroke-width="2"/><path d="M10 24c2-5 18-5 20 0M20 20v10" stroke="#f5f3ee" stroke-width="1.5"/></svg><span>Future Stadium<small>Design your own</small></span></div>
    <div class="top-meta"><span class="museum-label">Qatar Olympic &amp; Sports Museum</span>${state.session ? '<span>Touchscreen experience</span>' : '<span>Sports &amp; Architecture</span>'}</div>
  </header><main>${state.notice ? `<div class="toast-ok" role="status" style="margin-bottom:18px">${escapeHtml(state.notice)}</div>` : ''}${content}</main>
  <footer class="footer">A stadium concept made from your imagination</footer>
  <div class="connection-banner" role="alert" ${state.error ? '' : 'hidden'}>${escapeHtml(state.error)}</div>`;
}

function renderBoot() {
  return shell(`<section class="loading-view"><div class="loader-orbit"></div><h2>Preparing your design studio</h2><p class="muted">Connecting to the stadium archive…</p></section>`);
}

function renderHome() {
  const provider = state.health?.provider || 'unknown';
  const online = state.health?.status === 'ok';
  return shell(`<section class="home-grid">
    <div class="home-copy"><p class="eyebrow">Sports &amp; Architecture · QMA</p>
      <h1>Imagine a stadium<br>that is <span>only yours.</span></h1>
      <p class="lead">Choose the setting, shape and details. Then reveal a stadium of tomorrow, designed around your ideas.</p>
      <button class="button" data-action="start" ${!online || state.requestPending ? 'disabled' : ''}>Start designing <span class="button-arrow" aria-hidden="true">→</span></button>
      <div class="home-details"><span><i class="dot"></i> 15 design choices</span><span><i class="dot"></i> About 3–5 minutes</span><span><i class="dot"></i> ${online ? 'Ready to begin' : 'Connecting…'}</span></div>
    </div><div class="hero-art">${art()}</div>
  </section>${state.health?.status === 'low_storage' ? '<div class="mock-banner" style="margin-top:16px"><span class="mock-dot"></span>Station storage is low. Please ask a staff member for help.</div>' : ''}
  <span class="sr-only">Image generation mode: ${escapeHtml(provider)}${state.health?.is_mock ? ', test schematic' : ''}</span>`);
}

function valueFor(question) {
  return state.answers[question.id];
}

export function canContinue(question) {
  const value = valueFor(question);
  if (question.type === 'signature') return value?.mode === 'surprise' || (value?.mode === 'text' && value.text?.trim());
  if (question.type === 'multiple') return Array.isArray(value) && value.length >= question.min_selections;
  return typeof value === 'string' && value.length > 0;
}

function renderProgress(index) {
  const total = state.questionnaire.questions.length;
  return `<div class="progress-wrap"><div class="progress-labels"><span><strong>Design journey</strong></span><span>Question ${index + 1} of ${total}</span></div><div class="progress-track" role="progressbar" aria-label="Question progress" aria-valuemin="1" aria-valuemax="${total}" aria-valuenow="${index + 1}"><div class="progress-fill" style="width:${((index + 1) / total) * 100}%"></div></div></div>`;
}

function optionCard(question, option, selected, multiple, disabled = false) {
  return `<button type="button" class="option-card ${multiple ? 'multiple' : ''} ${selected ? 'selected' : ''}" role="${multiple ? 'checkbox' : 'radio'}" aria-checked="${selected}" data-action="choose" data-question="${escapeHtml(question.id)}" data-option="${escapeHtml(option.id)}" ${disabled ? 'disabled' : ''}>
    <span class="option-icon">${icon(question.id)}</span><span class="option-copy">${escapeHtml(option.label)}</span><span class="option-check" aria-hidden="true">${selected ? '✓' : ''}</span>
  </button>`;
}

function renderQuestion() {
  const question = state.questionnaire.questions[state.questionIndex];
  if (!question) { state.phase = 'review'; return renderReview(); }
  const isMultiple = question.type === 'multiple';
  let body;
  if (question.type === 'signature') {
    const value = valueFor(question);
    const surprise = value?.mode === 'surprise';
    body = `<div class="signature-form" role="radiogroup" aria-label="Choose your signature feature option">
      ${optionCard(question, {id:'surprise',label:'Surprise me — invent a feature that fits my design'}, surprise, false)}
    </div>${state.questionnaire.free_text_enabled ? `<label class="signature-form" style="margin-top:14px" for="signature-input"><span class="muted" style="font-size:13px;font-weight:600">Or describe your own feature</span><input class="signature-input" id="signature-input" maxlength="140" value="${escapeHtml(value?.mode === 'text' ? value.text : '')}" placeholder="A spiralling public walkway…" autocomplete="off"><span class="signature-meter"><span>Keep it short and suitable for everyone</span><span id="signature-count">${value?.text?.length || 0} / 140</span></span></label>` : '<p class="surprise-note">Custom text is being prepared for a future version. Choose “Surprise me” for this prototype.</p>'}</div>`;
  } else {
    const selected = valueFor(question);
    body = `<div class="option-grid" role="${isMultiple ? 'group' : 'radiogroup'}" aria-label="${escapeHtml(question.title)}">${question.options.map(option => {
      const active = isMultiple ? (selected || []).includes(option.id) : selected === option.id;
      const blocked = isMultiple && !active && (selected || []).length >= question.max_selections;
      return optionCard(question, option, active, isMultiple, blocked);
    }).join('')}</div>${isMultiple ? `<div class="selection-limit"><span class="selected-count">${(selected || []).length}</span> / ${question.max_selections} selected · Choose up to ${question.max_selections}</div>` : ''}`;
  }
  const title = question.type === 'signature' ? 'What would make your stadium unforgettable?' : question.title;
  const hint = isMultiple ? `Choose up to ${question.max_selections}` : question.type === 'signature' ? 'Choose a surprise feature' : 'Choose one';
  const nextLabel = state.questionIndex === state.questionnaire.questions.length - 1 ? 'Review my choices' : 'Continue';
  return shell(`<section class="step-shell">${renderProgress(state.questionIndex)}
    <div class="question-head"><span class="question-count">${String(question.number).padStart(2,'0')} <span aria-hidden="true">/</span> ${state.questionnaire.questions.length}</span><h2>${escapeHtml(title)}</h2><p class="selection-hint">${hint}</p></div>
    ${body}
    <div class="survey-nav"><button type="button" class="button ghost" data-action="back">← <span>${state.questionIndex === 0 ? 'Exit' : 'Back'}</span></button><div class="survey-nav-right"><button type="button" class="button secondary small" data-action="review">Review</button><button type="button" class="button" data-action="continue" ${canContinue(question) ? '' : 'disabled'}>${nextLabel}<span class="button-arrow" aria-hidden="true">→</span></button></div></div>
  </section>`);
}

function displayAnswer(question, answer) {
  if (question.id === 'signature') return answer?.mode === 'text' ? answer.text : 'Surprise me';
  const labels = Object.fromEntries(question.options.map(option => [option.id, option.label]));
  if (Array.isArray(answer)) return answer.map(id => labels[id] || id).join(' · ');
  return labels[answer] || answer || '—';
}

function renderReview() {
  const questions = state.questionnaire.questions;
  const entries = questions.filter(q => state.answers[q.id] !== undefined).map(q => `<div class="review-row"><span class="review-row-label">${String(q.number).padStart(2,'0')} · ${escapeHtml(q.title)}</span><span class="review-row-value">${escapeHtml(displayAnswer(q,state.answers[q.id]))}</span></div>`).join('');
  const notes = state.review?.notes_to_confirm || [];
  const warning = state.health?.is_mock ? `<div class="mock-banner" style="margin-top:16px"><span class="mock-dot"></span><span>This demo uses a labelled test schematic. Your choices and design story will be saved with it.</span></div>` : '';
  return shell(`<section class="step-shell">${renderProgress(state.questionnaire.questions.length - 1)}
    <div class="review-card"><div class="review-intro"><div><p class="eyebrow">One last look</p><h2>Your stadium, your choices.</h2><p class="muted" style="margin:0;font-size:14px">Check your selections before we create the final image.</p></div><button type="button" class="button secondary small" data-action="edit">Edit</button></div>
    <div class="review-answers">${entries}</div>
    ${notes.length ? `<div class="review-note"><h3>A quick design note</h3>${notes.map(note => `<p>${escapeHtml(note.message)}</p>`).join('')}<p style="margin-top:10px;font-weight:600">These notes keep your choices intact and guide how the concept is shown. Continue to confirm.</p></div>` : ''}</div>
    ${warning}<div class="survey-nav"><button type="button" class="button ghost" data-action="edit">← Edit choices</button><div class="survey-nav-right"><button type="button" class="button" data-action="generate" ${state.requestPending ? 'disabled' : ''}>Create my stadium <span class="button-arrow" aria-hidden="true">→</span></button></div></div>
  </section>`);
}

function renderGenerating() {
  const status = state.job?.status;
  let current = status === 'saving' ? 'Saving your design' : status === 'queued' ? 'Joining the design queue' : 'Creating your stadium';
  let detail = state.health?.is_mock ? 'Drawing a clearly labelled development schematic.' : 'The image is taking shape. Your answers are safely saved.';
  return shell(`<section class="loading-view" aria-live="polite"><div class="loader-orbit"></div><p class="eyebrow">Your stadium is taking shape</p><h2>${escapeHtml(current)}</h2><p class="muted">${escapeHtml(detail)}</p><div class="loading-progress"><span></span></div><div class="loading-steps"><span class="active">01 &nbsp; Building the concept</span><span class="${status === 'saving' ? 'active' : ''}">02 &nbsp; Saving your design</span><span>03 &nbsp; Ready to reveal</span></div><p class="muted" style="margin:24px 0 0;font-size:12px">Please keep this screen open.</p></section>`);
}

function renderError() {
  const error = state.job?.error;
  return shell(`<section class="loading-view"><div style="font-size:42px;color:#a64436;margin-bottom:14px" aria-hidden="true">!</div><p class="eyebrow" style="color:#a64436">A small pause</p><h2>We couldn't finish this image</h2><p class="muted">${escapeHtml(error?.message || 'Your answers are saved. Please try again or ask a staff member for help.')}</p><div class="survey-nav" style="text-align:left"><button class="button secondary" data-action="edit">Review choices</button><button class="button" data-action="retry">Try again</button></div></section>`);
}

function renderResult() {
  const result = state.job.result;
  const design = result.design;
  const mock = state.job.is_mock;
  const questions = state.questionnaire.questions;
  const choice = key => displayAnswer(questions.find(q=>q.id===key),result.answers[key]);
  const facts = [['Theme & style', `${choice('theme')} · ${choice('style')}`], ['Signature feature', design.signature], ['Innovation', choice('innovation')], ['Technology', choice('technologies')], ['Future legacy', choice('legacy')]];
  return shell(`<section class="reveal-grid">
    <figure class="result-art"><img src="${escapeHtml(result.image_url)}" alt="${mock ? 'Labelled test schematic for' : 'AI generated concept of'} ${escapeHtml(design.title)}"/><figcaption><span>${mock ? 'Development test schematic' : 'AI concept visualisation'}</span><span>${result.image.width} × ${result.image.height}</span></figcaption></figure>
    <div class="result-copy"><p class="eyebrow">Your stadium is ready</p><h1>${escapeHtml(design.title)}</h1><div class="capacity-chip">◎ &nbsp; ${escapeHtml(design.capacity)} spectators</div>
      ${mock ? '<div class="mock-banner" style="margin:0 0 17px"><span class="mock-dot"></span>Test schematic — not an AI generated stadium image.</div>' : ''}
      <p class="story">${escapeHtml(design.summary)}</p><div class="result-facts">${facts.map(([label,value])=>`<div><div class="fact-label">${escapeHtml(label)}</div><div class="fact-value">${escapeHtml(value)}</div></div>`).join('')}</div>
      <div class="result-actions"><button class="button" data-action="finish">Finish experience <span class="button-arrow" aria-hidden="true">→</span></button><a class="button secondary" href="${escapeHtml(result.image_url)}" download="${escapeHtml(design.title.toLowerCase().replace(/[^a-z0-9]+/g,'-'))}.png">Save image ↓</a></div>
      <p class="reference-line">Saved to the museum archive · <strong>${escapeHtml(result.archive_reference)}</strong></p>
    </div>
  </section>`);
}

export function render() {
  const views = {boot: renderBoot, home: renderHome, question: renderQuestion, review: renderReview,
    generating: renderGenerating, error: renderError, result: renderResult};
  app.innerHTML = (views[state.phase] || renderHome)();
  document.body.dataset.phase = state.phase;
}


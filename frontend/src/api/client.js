export async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? {'Content-Type':'application/json'} : {}), ...options.headers },
  });
  const type = response.headers.get('content-type') || '';
  const body = type.includes('application/json') ? await response.json() : null;
  if (!response.ok) {
    let message = body?.detail;
    if (message && typeof message === 'object') message = message.message || JSON.stringify(message);
    throw new Error(typeof message === 'string' ? message : `Request failed (${response.status}). Please try again.`);
  }
  return body;
}


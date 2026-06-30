const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL

function buildUrl(path) {
  return `${API_BASE_URL}${path}`
}

async function parseResponse(response) {
  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    const detail =
      (data && typeof data === 'object' && 'detail' in data && data.detail) ||
      `Request failed with status ${response.status}`
    throw new Error(typeof detail === 'string' ? detail : `Request failed with status ${response.status}`)
  }

  return data
}

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {})

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(buildUrl(path), {
    ...options,
    headers,
  })

  return parseResponse(response)
}

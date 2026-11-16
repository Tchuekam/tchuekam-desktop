export const getAgentDetails = async (agentId, options = {}) => {
  const backendOrigin = (() => {
    const envUrl = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_HERMES_API_URL)
      ? String(import.meta.env.VITE_HERMES_API_URL).replace(/\/+$/, '')
      : '';
    if (envUrl) return envUrl;
    if (typeof window !== 'undefined' && window.location?.hostname?.endsWith('.vercel.app') && !window.__HERMES_SESSION_TOKEN__) {
      return 'https://tchuekam-agent-production.up.railway.app';
    }
    return '';
  })();
  const defaultBaseUrl =
    typeof window !== "undefined" && window.location?.protocol?.startsWith("http")
      ? `${backendOrigin}/api/muapi-proxy/agents`
      : "http://127.0.0.1:8000/agents";
  const {
    baseUrl = defaultBaseUrl, // Default relative URL in web deployments, loopback in local Electron/dev
    fetchOptions = {}
  } = options;

  if (!agentId) {
    throw new Error("Agent ID is required");
  }

  const url = `${baseUrl}/${agentId}`;
  
  try {
    const response = await fetch(url, {
      ...fetchOptions,
      cache: fetchOptions.cache || 'no-store', 
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch agent details: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error fetching agent details:", error);
    throw error;
  }
};

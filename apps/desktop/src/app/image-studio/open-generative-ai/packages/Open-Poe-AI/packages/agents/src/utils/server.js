export const getAgentDetails = async (agentId, options = {}) => {
  const defaultBaseUrl =
    typeof window !== "undefined" && window.location?.protocol?.startsWith("http")
      ? "/api/muapi-proxy/agents"
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

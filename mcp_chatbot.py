#成功！
#先运行research_server.py    的文件；
# mcp_project/mcp_chatbot.py   添加resource与prompts
import os
import json
import asyncio
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

import httpx

# # ---------------------------
# # UIUI / OpenAI-compatible API settings
# # ---------------------------
# BASE_URL = "https://sg.uiuiapi.com"
# CHAT_URL = f"{BASE_URL}/v1/chat/completions"

# UIUI_API_KEY = os.getenv("UIUI_API_KEY", "sk-6kxUngAXqtc8FcPqfbK7tqu2wpV8aMSINzFJHQiR1V9denB6")  # 建议只用环境变量
# if not UIUI_API_KEY or UIUI_API_KEY == "sk-6kxUngAXqtc8FcPqfbK7tqu2wpV8aMSINzFJHQiR1V9denB6":
#     raise RuntimeError("Missing UIUI_API_KEY. Please export UIUI_API_KEY before running.")

# HEADERS = {
#     "Authorization": f"Bearer {UIUI_API_KEY}",
#     "Content-Type": "application/json",
# }

# MODEL = "claude-sonnet-4-5-20250929"



# ---------------------------
# UIUI / OpenAI-compatible API settings
# ---------------------------
BASE_URL = "https://sg.uiuiapi.com"
CHAT_URL = f"{BASE_URL}/v1/chat/completions"

# 优先使用环境变量；若未设置，则使用下方回退 key（建议把实际 key 放到环境变量中）
UIUI_API_KEY = os.getenv("UIUI_API_KEY", "sk-6kxUngAXqtc8FcPqfbK7tqu2wpV8aMSINzFJHQiR1V9denB6")
if not UIUI_API_KEY:
    raise RuntimeError("Missing UIUI_API_KEY. Please export UIUI_API_KEY before running.")

HEADERS = {
    "Authorization": f"Bearer {UIUI_API_KEY}",
    "Content-Type": "application/json",
}

# 注意：MODEL 必须是 UIUI 已为你开通并配置价格/倍率的模型名
MODEL = "claude-sonnet-4-5-20250929"



async def call_uiui_async(payload: Dict[str, Any], timeout: int = 90) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(CHAT_URL, headers=HEADERS, json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
        return r.json()

# ---------------------------
# MCP Chatbot implementation
# ---------------------------
class MCP_ChatBot:
    def __init__(self):
        self.exit_stack = AsyncExitStack()

        # Keep a list of all sessions (for cleanup)
        self.sessions: List[ClientSession] = []

        # Maps for routing
        self.tool_to_session: Dict[str, ClientSession] = {}
        self.resource_to_session: Dict[str, ClientSession] = {}
        self.prompt_to_session: Dict[str, ClientSession] = {}

        # OpenAI-style tool specs (for UIUI tool calling if supported)
        self.available_tools: List[Dict[str, Any]] = []
        self.available_prompts: List[Dict[str, Any]] = []

    async def connect_to_server(self, server_name: str, server_config: dict) -> None:
        """Connect to one MCP server and collect tools/resources/prompts if supported."""
        server_params = StdioServerParameters(**server_config)

        read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self.sessions.append(session)

        # ---- tools (almost always supported) ----
        tools_resp = await session.list_tools()
        tools = tools_resp.tools
        print(f"\nConnected to {server_name} with tools:", [t.name for t in tools])

        for tool in tools:
            self.tool_to_session[tool.name] = session
            self.available_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema or {"type": "object"},
                }
            })

        # ---- resources (optional capability) ----
        try:
            res_resp = await session.list_resources()
            if res_resp and getattr(res_resp, "resources", None):
                for r in res_resp.resources:
                    self.resource_to_session[str(r.uri)] = session
                print(f"  {server_name}: resources enabled ({len(res_resp.resources)} items)")
        except Exception as e:
            # Many servers don't implement this; do NOT treat as fatal
            print(f"  {server_name}: list_resources not supported ({e})")

        # ---- prompts (optional capability) ----
        try:
            p_resp = await session.list_prompts()
            if p_resp and getattr(p_resp, "prompts", None):
                for p in p_resp.prompts:
                    self.prompt_to_session[p.name] = session
                    self.available_prompts.append({
                        "name": p.name,
                        "description": p.description or "",
                        "arguments": p.arguments or [],
                    })
                print(f"  {server_name}: prompts enabled ({len(p_resp.prompts)} items)")
        except Exception as e:
            print(f"  {server_name}: list_prompts not supported ({e})")

    async def connect_to_servers(self):
        with open("server_config.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        servers = data.get("mcpServers", {})
        for server_name, server_config in servers.items():
            try:
                await self.connect_to_server(server_name, server_config)
            except Exception as e:
                print(f"Failed to connect to {server_name}: {e}")

    async def process_query(self, query: str):
        messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]

        while True:
            payload: Dict[str, Any] = {
                "model": MODEL,
                "messages": messages,
                "max_tokens": 1024,
                "tools": self.available_tools,
                "tool_choice": "auto",
            }

            data = await call_uiui_async(payload)

            # OpenAI-style
            msg = data["choices"][0].get("message", {})
            assistant_text = msg.get("content")
            if assistant_text:
                print(assistant_text if isinstance(assistant_text, str) else json.dumps(assistant_text, ensure_ascii=False))

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                break

            messages.append(msg)

            for tc in tool_calls:
                tc_id = tc.get("id")
                fn = tc.get("function", {})
                tool_name = fn.get("name")
                raw_args = fn.get("arguments", "{}")

                try:
                    tool_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    tool_args = {}

                print(f"[MCP] Calling tool {tool_name} with args={tool_args}")

                session = self.tool_to_session.get(tool_name)
                if session is None:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": f"ERROR: tool {tool_name} not available"
                    })
                    continue

                try:
                    result = await session.call_tool(tool_name, arguments=tool_args)
                    tool_result_text = getattr(result, "content", result)
                    if not isinstance(tool_result_text, str):
                        tool_result_text = str(tool_result_text)
                except Exception as e:
                    tool_result_text = f"ERROR executing tool {tool_name}: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": tool_result_text
                })

    async def get_resource(self, resource_uri: str):
        session = self.resource_to_session.get(resource_uri)

        # fallback for papers://... : find any papers resource provider
        if not session and resource_uri.startswith("papers://"):
            for uri, sess in self.resource_to_session.items():
                if uri.startswith("papers://"):
                    session = sess
                    break

        if not session:
            print(f"Resource '{resource_uri}' not found (no server provides it).")
            return

        try:
            result = await session.read_resource(uri=resource_uri)
            if result and getattr(result, "contents", None):
                print(f"\nResource: {resource_uri}\n")
                print(result.contents[0].text)
            else:
                print("No content available.")
        except Exception as e:
            print(f"Error reading resource: {e}")

    async def list_prompts(self):
        if not self.available_prompts:
            print("No prompts available.")
            return
        print("\nAvailable prompts:")
        for p in self.available_prompts:
            print(f"- {p['name']}: {p['description']}")

    async def execute_prompt(self, prompt_name: str, args: Dict[str, str]):
        session = self.prompt_to_session.get(prompt_name)
        if not session:
            print(f"Prompt '{prompt_name}' not found.")
            return

        try:
            result = await session.get_prompt(prompt_name, arguments=args)
            if result and getattr(result, "messages", None):
                content = result.messages[0].content
                text = content if isinstance(content, str) else str(content)
                print(f"\nExecuting prompt '{prompt_name}'...\n")
                await self.process_query(text)
            else:
                print("Prompt returned no messages.")
        except Exception as e:
            print(f"Error executing prompt: {e}")

    async def chat_loop(self):
        print("\nMCP Chatbot Started!")
        print("Type your queries or 'quit' to exit.")
        print("Use @folders / @<topic> only if a server provides papers:// resources")
        print("Use /prompts to list prompts; /prompt <name> a=b to execute")

        while True:
            query = input("\nQuery: ").strip()
            if not query:
                continue
            if query.lower() == "quit":
                break

            # @resource shortcut
            if query.startswith("@"):
                topic = query[1:].strip()
                resource_uri = "papers://folders" if topic == "folders" else f"papers://{topic}"
                await self.get_resource(resource_uri)
                continue

            # slash commands
            if query.startswith("/"):
                parts = query.split()
                cmd = parts[0].lower()
                if cmd == "/prompts":
                    await self.list_prompts()
                elif cmd == "/prompt":
                    if len(parts) < 2:
                        print("Usage: /prompt <name> <arg1=value1> <arg2=value2>")
                        continue
                    name = parts[1]
                    args = {}
                    for a in parts[2:]:
                        if "=" in a:
                            k, v = a.split("=", 1)
                            args[k] = v
                    await self.execute_prompt(name, args)
                else:
                    print(f"Unknown command: {cmd}")
                continue

            # normal LLM query
            try:
                await self.process_query(query)
            except Exception as e:
                print(f"Error: {e}")

    async def cleanup(self):
        await self.exit_stack.aclose()

async def main():
    bot = MCP_ChatBot()
    try:
        await bot.connect_to_servers()
        await bot.chat_loop()
    finally:
        await bot.cleanup()


if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
        # 如果能取到 running loop，说明在 Jupyter / IPython 中
        # 直接创建任务运行
        loop.create_task(main())
    except RuntimeError:
        # 没有 running loop，说明在普通脚本环境
        asyncio.run(main())

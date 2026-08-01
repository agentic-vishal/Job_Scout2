import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from streamlit.testing.v1 import AppTest

import agent
import mcp_server


class ScoutTests(unittest.TestCase):
    def test_tracker_write(self):
        with tempfile.TemporaryDirectory() as directory:
            tracker = Path(directory) / "applications.json"
            tracker.write_text("[]", encoding="utf-8")
            with patch.object(mcp_server, "TRACKER", tracker):
                mcp_server.save_application("Acme", "Engineer", 82, "Python")

            saved = json.loads(tracker.read_text(encoding="utf-8"))
            self.assertEqual(saved[0]["fit_score"], 82)

    def test_private_urls_are_blocked(self):
        with self.assertRaises(ValueError):
            mcp_server.public_url("http://127.0.0.1/private")

    def test_streamlit_first_load(self):
        app = AppTest.from_file("app.py").run(timeout=15)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Scout")
        self.assertEqual(app.text_area[0].label, "Job description or posting URL")

    def test_streamlit_explains_missing_openai_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            app = AppTest.from_file("app.py").run(timeout=15)
            app.text_area[0].input("Python engineer at Acme")
            app.button[0].click().run(timeout=15)

        self.assertIn("OPENAI_API_KEY is missing", app.error[0].value)

    def test_openai_configuration_template(self):
        template = Path(".env.example").read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY=", template)
        self.assertIn("OPENAI_MODEL=", template)
        self.assertNotIn("GOOGLE_", template)

    def test_responses_content_blocks_become_text(self):
        message = AIMessage(content=[{"type": "text", "text": "Fit score: 80/100"}])
        self.assertEqual(agent.message_text(message), "Fit score: 80/100")


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_requires_openai_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                await agent.scout("Python engineer at Acme")

    async def test_tool_contract(self):
        server = StdioServerParameters(
            command=sys.executable,
            args=[str(Path("mcp_server.py").resolve())],
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertEqual(
                    {tool.name for tool in tools},
                    {"web_search", "fetch_url", "get_resume", "save_application"},
                )
                result = await session.call_tool("get_resume", {})
                self.assertIn("Your Name", result.content[0].text)

    async def test_agent_executes_requested_tool(self):
        calls = []

        @tool
        def get_resume() -> str:
            """Load the candidate resume."""
            calls.append("get_resume")
            return "Python engineer"

        class FakeModel:
            def __init__(self):
                self.parallel_tool_calls = None
                self.responses = iter(
                    [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "get_resume",
                                    "args": {},
                                    "id": "call-1",
                                    "type": "tool_call",
                                }
                            ],
                        ),
                        AIMessage(content="Fit score: 80/100"),
                    ]
                )

            def bind_tools(self, tools, **kwargs):
                self.parallel_tool_calls = kwargs.get("parallel_tool_calls")
                return self

            async def ainvoke(self, messages):
                return next(self.responses)

        trace = []
        model = FakeModel()
        graph = agent.build_graph(model, [get_resume], trace.append)
        result = await graph.ainvoke(
            {"messages": [("user", "Python engineer at Acme")]}
        )

        self.assertEqual(result["messages"][-1].content, "Fit score: 80/100")
        self.assertTrue(any(isinstance(message, ToolMessage) for message in result["messages"]))
        self.assertEqual(calls, ["get_resume"])
        self.assertEqual(trace, ["→ get_resume"])
        self.assertFalse(model.parallel_tool_calls)


if __name__ == "__main__":
    unittest.main()

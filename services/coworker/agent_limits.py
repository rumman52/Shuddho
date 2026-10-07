"""Dependency-free Core Agent execution limits.

Keep safety ceilings here so evaluation/CI code can share the exact runtime
contract without importing ORM/provider infrastructure.
"""

AGENT_MAX_TOOL_STEPS = 8

"""AIAquafarm LangGraph multi-agent orchestration package.

Agents:
    management_agent:   Top-level orchestrator — coordinates sub-agents and
                        routes decisions to the optimization agent.
    optimization_agent: Synthesises AI module outputs into control commands
                        and interfaces with the RASbit digital twin.

TODO (Phase 3): Implement full LangGraph workflow graphs.
"""

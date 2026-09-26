from langgraph.graph import END, START, StateGraph

from aisdlc.graph.nodes import discover, human_approval
from aisdlc.graph.router import route
from aisdlc.graph.state import AgentState

# 1. Initialize the Graph with our shared state
workflow = StateGraph(AgentState)

# 2. Add the nodes
workflow.add_node("discover", discover)
workflow.add_node("human_approval", human_approval)

# 3. Define the edges (the flow)
workflow.add_edge(START, "discover")

# discover -> router (Conditional Edge)
# The router function decides which node to visit next
workflow.add_conditional_edges(
    "discover", 
    route,
    {
        "discover": "discover",     # Loop back if still needs discovery
        "human_approval": "human_approval",  # Route to human approval node
        "__end__": END,
    }
)

# 4. Pause before a human-owned transition. Resuming requires an explicit approval.
app = workflow.compile(interrupt_before=["human_approval"])
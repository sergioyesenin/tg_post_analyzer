# event/routing
Route the event case to the proper synthesis depth.

Decision goals:
- classify evidence strength: sufficient, limited, weak-signal, insufficient
- mark whether retrieval is required by policy
- choose conservative fallback when signals conflict

Output contract:
- one compact JSON object with routing flags
- deterministic labels only (no free-form synonyms)
- never override sufficiency inputs from context stage


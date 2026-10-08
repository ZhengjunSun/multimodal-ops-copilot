# Five-minute demo

1. Start `uvicorn ops_copilot.api:app --reload --port 8010`.
2. Create an incident and upload a synthetic `.log`, `.png`, and `.wav` file.
3. Ask for an incident timeline and watch WebSocket stages arrive.
4. Interrupt one run, verify the session becomes `interrupted`, then start a new analysis.
5. Ask to `restart the affected component`; inspect the approval gate.
6. Approve or reject and verify that no real action is executed.

The default provider works without credentials and all demo inputs should be synthetic.


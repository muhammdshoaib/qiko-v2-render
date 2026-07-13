"""Finance: a native property-portfolio financial-analytics worker vertical.

Replaces the external Excel-analytics microservice (excel-agent-server / el-backend.qiko.ai):
it ingests property-portfolio Excel workbooks, computes financial analytics (per-property
income/expenses/net-profit/margin/risk, vendor + expense-category breakdowns, portfolio summary,
insights and trends), and answers grounded chat questions over the data via the LLM gateway.

The *computation* is a faithful Python port of the excel-agent-server analyzer
(qiko-mcp-parser src/analyzer.ts); the eval/Pinecone infra is intentionally NOT ported. Follows
the app.modules.sales_intelligence pattern: dataclasses + Protocol stores (in-memory default,
Postgres-backed behind the same protocol -- see app/db/stores.py), a tenant-scoped router
(app/modules/finance/router.py) and a service orchestrator (service.py).
"""

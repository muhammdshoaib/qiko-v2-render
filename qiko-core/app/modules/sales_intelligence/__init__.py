"""IDG Sales Intelligence: real UNGM/TED tender ingestion, deterministic bid/no-bid
qualification, human review, and Salesforce push -- ported from the unmerged qiko-backend
`origin/idg-sales` Laravel branch (app/Services/IdgSales, app/Http/Controllers/Api/IdgSales,
app/Models/IdgSales*). See router.py for the HTTP surface and service.py/salesforce.py for the
faithfully-ported business logic.
"""

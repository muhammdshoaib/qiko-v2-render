"""Qiko Intelligence Worker: a multi-source status worker with grounded chat.

The problem it exists for is that no system in the stack can contradict another. Slack holds what
people say they did, Qiko Track holds what was moved on a board, and GitHub holds what actually
shipped. None of the three can see the other two, so nobody can get a status that does not depend
on asking the person whose work is being reported on.

This vertical reads all three, normalises what they emit into one `Signal`, ingests it so it is
retrievable, and answers questions grounded in it.

Layout follows `app.modules.finance` (models / service / chat / router, Protocol stores with an
in-memory default and Postgres behind the same protocol) and the source catalog follows
`app.modules.sales_intelligence.source_catalog`. Neither pattern is new here; the composition is.

Two invariants run through the whole module and are worth stating once:

EVERY READ IS SCOPED BY TENANT **AND** AGENT. A signal belongs to one worker. The Slack foundation
this grew out of scoped only by tenant, which would have let two workers in the same tenant share
a buffer and summarise each other's conversations.

A SOURCE OF RECORD IS EVIDENCE; THIS WORKER'S OWN OUTPUT IS NOT. Research findings and uploaded
documents are signals so they can be retrieved and cited, but they carry no `ref` and must never
be treated as proof that work happened. Only Qiko Track and GitHub can say that.
"""

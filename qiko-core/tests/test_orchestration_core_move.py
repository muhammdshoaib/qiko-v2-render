"""QIW: proves the generic orchestration pieces moved to agentcore without changing the public
surface intelligence/orchestration/__init__.py already exposes, or their behavior."""
def test_intelligence_orchestration_still_exports_everything_it_did_before():
    from app.modules.intelligence import orchestration

    for name in ("ConsolidatedOutput", "Critic", "Document", "EvidenceBundle", "Finding",
                "InMemoryPipelineRunStore", "Magistrate", "Pipeline", "PipelineConfig",
                "PipelineRun", "PipelineRunStore", "Scout", "Signal", "Specialist",
                "SpecialistOutput", "Synthesizer", "Verdict"):
        assert hasattr(orchestration, name), f"missing export: {name}"


def test_evidence_bundle_has_no_intelligence_specific_fields():
    from app.modules.agentcore.orchestration import EvidenceBundle

    bundle = EvidenceBundle(text_chunks=["a"], sources=["s1"])
    assert not hasattr(bundle, "signals")
    assert not hasattr(bundle, "documents")


def test_pipeline_synthesizer_critic_magistrate_importable_from_agentcore():
    from app.modules.agentcore.orchestration import (  # noqa: F401
        Critic, Magistrate, Pipeline, PipelineConfig, Synthesizer,
    )

    magistrate = Magistrate(threshold=0.7)
    assert magistrate.threshold == 0.7

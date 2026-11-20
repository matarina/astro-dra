"""Installed report-boundary checks with no model/network calls."""
from local_deep_research.report_generator import IntegratedReportGenerator


def test_detailed_report_uses_explicit_snapshot_and_preserves_question():
    generator = IntegratedReportGenerator.__new__(IntegratedReportGenerator)
    generator.settings_snapshot = {"report.output_mode":"field_extraction",
                                   "report.requested_fields":["population", "technology"]}
    seen = []
    def stop_at_structure(initial, query):
        seen.append(query)
        raise RuntimeError("evaluation stopped before model calls")
    generator._determine_report_structure = stop_at_structure
    question = "Explain Chinese hamster stable gene expression from a 2020 cohort."
    try:
        generator.generate_report({}, question)
    except RuntimeError as error:
        assert str(error) == "evaluation stopped before model calls"
    assert seen == [question]
    assert generator._research_spec.output_mode == "field_extraction"
    assert generator._research_spec.language is None
    assert generator._research_spec.year_from is None
    assert "explicit_settings" in generator._scope_contract


def test_detailed_report_without_settings_does_not_append_guessed_contract():
    generator = IntegratedReportGenerator.__new__(IntegratedReportGenerator)
    generator.settings_snapshot = {}
    generator._determine_report_structure = lambda *args: (_ for _ in ()).throw(RuntimeError("stop"))
    try:
        generator.generate_report({}, "Find 20 English papers and extract platform fields.")
    except RuntimeError as error:
        assert str(error) == "stop"
    assert generator._scope_contract == ""
    assert generator._research_spec.requested_count is None

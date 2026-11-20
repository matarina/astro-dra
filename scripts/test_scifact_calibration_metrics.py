"""Ensure calibration missingness and error classes cannot inflate agreement."""
from collect_scifact_calibration import classification


def test_missing_and_partial_remain_in_accuracy_denominator():
    gold = {"a": {"expected": "SUPPORT", "task_family": "one"},
            "b": {"expected": "NEI", "task_family": "two"},
            "c": {"expected": "CONTRADICT", "task_family": "three"}}
    rows = {"a": {"prediction": "SUPPORT"}, "b": {"prediction": "PARTIAL"}}
    result = classification(rows, gold, "prediction")
    assert result["all_scheduled_accuracy"]["numerator"] == 1
    assert result["all_scheduled_accuracy"]["denominator"] == 3
    assert result["missing"] == 1 and result["partial_unmapped"] == 1
    assert result["three_class_prediction_coverage"]["numerator"] == 1


def test_false_support_and_contradiction_are_separate():
    gold = {"a": {"expected": "SUPPORT", "task_family": "one"},
            "b": {"expected": "NEI", "task_family": "two"},
            "c": {"expected": "CONTRADICT", "task_family": "three"}}
    rows = {"a": {"prediction": "SUPPORT"}, "b": {"prediction": "SUPPORT"},
            "c": {"prediction": "NEI"}}
    result = classification(rows, gold, "prediction")
    assert result["support_precision"]["numerator"] == 1
    assert result["support_precision"]["denominator"] == 2
    assert result["false_support_on_non_support"]["numerator"] == 1
    assert result["false_support_on_non_support"]["denominator"] == 2
    assert result["recall_by_gold_label"]["CONTRADICT"]["numerator"] == 0
    assert result["recall_by_gold_label"]["NEI"]["numerator"] == 0


def test_repeated_source_does_not_become_independent_clusters():
    gold = {str(i): {"expected": "SUPPORT", "task_family": "same"} for i in range(4)}
    rows = {str(i): {"prediction": "SUPPORT"} for i in range(4)}
    result = classification(rows, gold, "prediction")
    assert result["accuracy_document_cluster_bootstrap"]["task_families"] == 1
    assert result["accuracy_document_cluster_bootstrap"]["bootstrap95"] is None


if __name__ == "__main__":
    tests = [value for name, value in globals().copy().items() if name.startswith("test_")]
    for test in tests:
        test()
    print(str(len(tests))+" metric boundary checks passed")

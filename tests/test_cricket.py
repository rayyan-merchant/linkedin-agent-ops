from linkedin_agent_ops.agents.cricket import (
    CricketBuildLogAgent,
    CricketBuildLogRequest,
    CricketBuildLogResult,
    MetricChange,
    MetricDirection,
    ProjectMetric,
)


def test_cricket_validator_rejects_invented_metric():
    request = CricketBuildLogRequest(
        week_number=7,
        work_completed="Tracked the ball through the delivery sequence.",
        failures="Motion blur still causes missed detections.",
        current_metrics=[
            ProjectMetric(
                name="ball detection mAP",
                value=0.73,
                unit="mAP",
                better_when=MetricDirection.HIGHER,
            )
        ],
    )
    result = CricketBuildLogResult(
        week_headline="Week 7 reached 99 percent accuracy.",
        technical_to_cricket_translation=["Track release.", "Follow trajectory."],
        metric_changes=[
            MetricChange(
                name="ball detection mAP",
                previous=None,
                current="0.73 mAP",
                interpretation="Baseline established.",
            )
        ],
        progress_narrative="Tracking now covers the delivery sequence.",
        failure_narrative="Motion blur remains unresolved.",
        hook_options=["Hook one", "Hook two", "Hook three"],
        audience_bridge="The metric connects detection quality to usable analysis.",
        visual_recommendation="Show a trajectory overlay.",
    )
    issues = CricketBuildLogAgent.validate(result, request)
    assert any(issue.code == "invented_metric" for issue in issues)


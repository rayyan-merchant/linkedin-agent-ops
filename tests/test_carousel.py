from linkedin_agent_ops.agents.carousel import (
    CarouselAgent,
    CarouselRequest,
    CarouselResult,
    CarouselSlide,
    render_marp,
)
from linkedin_agent_ops.context import CreatorProfile


def build_result():
    return CarouselResult(
        narrative_strategy="Move from production problem to practical decision.",
        slides=[
            CarouselSlide(
                slide_number=index,
                title=f"Slide {index}",
                on_slide_copy="One focused production idea.",
                core_message="The reader understands one decision.",
                visual_recommendation="Simple architecture diagram.",
                transition_hook="The next constraint changes the choice.",
            )
            for index in range(1, 9)
        ],
        design_guidance=["One visual.", "High contrast.", "Consistent hierarchy."],
    )


def test_carousel_validation_and_marp_are_consistent():
    agent = CarouselAgent(
        runner=None,
        profile=CreatorProfile({"positioning": "AI engineer"}),
        examples_path="missing",
    )
    result = build_result()
    issues = agent.validate(
        result,
        CarouselRequest(
            topic="Agent reliability",
            key_points=["Tools fail.", "Retries need limits."],
            slide_count=8,
        ),
    )
    marp = render_marp(result)
    assert issues == []
    assert marp.count("\n---\n") == 8
    assert "# Slide 1" in marp


import pytest

from ai_clips_maker.metadata_suggestions import (
    generate_title_suggestions,
    validate_suggestion_output,
)


def test_suggestions_are_distinct_grounded_and_relevant():
    transcript = (
        "We learned how to build reliable garden irrigation systems. "
        "This method uses water more efficiently."
    )
    context = {
        "audience": "Home gardeners",
        "topic": "Water-saving irrigation",
        "goal": "Explain a practical technique",
        "tone": "Friendly and clear",
    }

    suggestions = generate_title_suggestions(transcript, context)

    assert len(suggestions["options"]) == 3
    assert len({option["title"] for option in suggestions["options"]}) == 3
    assert suggestions["options"][0]["title"] == (
        "We learned how to build reliable garden irrigation systems"
    )
    assert "Water-saving irrigation" in suggestions["options"][1]["title"]
    assert all(option["rationale"] for option in suggestions["options"])
    assert suggestions["hashtags"][0] == "#WaterSavingIrrigation"
    assert len(suggestions["hashtags"]) <= 4
    assert any("Verify" in note for note in suggestions["uncertainties"])
    validate_suggestion_output(suggestions)


def test_suggestion_schema_rejects_duplicate_titles():
    with pytest.raises(ValueError, match="distinct"):
        validate_suggestion_output({
            "summary": "Summary",
            "options": [
                {"title": "Same title", "rationale": "First"},
                {"title": "Same title", "rationale": "Second"},
                {"title": "Other title", "rationale": "Third"},
            ],
            "hashtags": ["#Relevant"],
            "uncertainties": [],
        })


def test_short_transcript_is_flagged_and_has_no_stuffed_tags():
    suggestions = generate_title_suggestions("Yes.", {})

    assert any("very short" in note for note in suggestions["uncertainties"])
    assert suggestions["hashtags"] == []
    assert len(suggestions["options"]) == 3

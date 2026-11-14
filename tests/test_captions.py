from types import SimpleNamespace

from ai_clips_maker.captions import streamer_tag_layout, write_ass_captions


def test_ass_captions_are_bold_high_contrast_word_timed_and_clipped(tmp_path):
    words = [
        SimpleNamespace(text="Hello", start_time=1.0, end_time=1.3),
        SimpleNamespace(text="there,", start_time=1.4, end_time=1.8),
        SimpleNamespace(text="friend!", start_time=1.9, end_time=2.3),
        SimpleNamespace(text="outside", start_time=10.0, end_time=10.5),
    ]

    output = write_ass_captions(words, 1.0, 3.0, tmp_path / "captions.ass")
    content = output.read_text(encoding="utf-8-sig")

    assert "Style: TikTok,Impact,76" in content
    assert "&H70000000,-1,0,0,0,100,100,0,0,3,5,1,2" in content
    assert "84,84,500,1" in content
    assert "{\\k30}HELLO {\\k40}THERE, {\\k40}FRIEND!" in content
    assert "outside" not in content
    assert "Dialogue: 0,0:00:00.00,0:00:01.30" in content


def test_ass_captions_wrap_long_text_into_readable_lines(tmp_path):
    words = [
        SimpleNamespace(text=f"word{index}", start_time=index * 0.3, end_time=index * 0.3 + 0.2)
        for index in range(5)
    ]

    output = write_ass_captions(words, 0.0, 3.0, tmp_path / "captions.ass")
    content = output.read_text(encoding="utf-8-sig")

    assert r"\N" in content


def test_streamer_tag_is_a_persistent_lower_right_overlay(tmp_path):
    output = write_ass_captions(
        [],
        2.0,
        22.0,
        tmp_path / "tagged.ass",
        streamer_tag=" SONICINSIDE ",
        streamer_tag_y=1240,
        caption_style="classic",
    )
    content = output.read_text(encoding="utf-8-sig")

    assert "Style: StreamerTag,Arial,34" in content
    assert (
        "Dialogue: 1,0:00:00.00,0:00:20.00,StreamerTag,,0,0,0,,"
        in content
    )
    assert (
        r"{\an3\pos(1008,1240)\fs34\bord6\3c&H000000&}SONICINSIDE"
    ) in content
    assert "Style: StreamerTag,Arial,34" in content
    assert "&HFF000000,-1,0,0,0,100,100,0,0,1,6,1,3" in content


def test_streamer_platform_marks_are_drawn_next_to_outlined_name(tmp_path):
    for platform in ("twitch", "kick"):
        output = write_ass_captions(
            [],
            0.0,
            20.0,
            tmp_path / f"{platform}.ass",
            streamer_tag="SONICINSIDE",
            streamer_platform=platform,
        )
        content = output.read_text(encoding="utf-8-sig")
        assert "SONICINSIDE" in content
        assert "\\p1" not in content
        assert "Dialogue: 1," in content


def test_streamer_tag_layout_reserves_space_for_attached_logo():
    tag_x, tag_y, font_size, logo = streamer_tag_layout(
        1080,
        1920,
        "SONICINSIDE",
        1872,
        has_platform_logo=True,
    )

    assert tag_x == 1008
    assert tag_y == 1872
    assert font_size == 34
    assert logo is not None
    logo_x, logo_y, logo_size = logo
    assert logo_x < tag_x
    assert logo_y < tag_y
    assert logo_size == 46


def test_streamer_platform_requires_a_supported_value(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="streamer_platform"):
        write_ass_captions(
            [],
            0.0,
            20.0,
            tmp_path / "invalid-platform.ass",
            streamer_tag="SONICINSIDE",
            streamer_platform="youtube",
        )


def test_streamer_tag_is_omitted_when_not_provided(tmp_path):
    output = write_ass_captions([], 0.0, 20.0, tmp_path / "untagged.ass")
    content = output.read_text(encoding="utf-8-sig")

    assert "Dialogue: 1," not in content


def test_editable_hook_is_a_persistent_top_panel(tmp_path):
    output = write_ass_captions(
        [],
        4.0,
        24.0,
        tmp_path / "hook.ass",
        hook_text="A concise hook for this particular clip",
    )
    content = output.read_text(encoding="utf-8-sig")

    assert "Style: Hook,Impact,70" in content
    assert (
        "Dialogue: 2,0:00:00.00,0:00:20.00,Hook,,0,0,0,,"
        in content
    )
    assert r"A CONCISE HOOK FOR THIS\NPARTICULAR CLIP" in content


def test_empty_hook_does_not_add_a_headline_event(tmp_path):
    output = write_ass_captions([], 0.0, 20.0, tmp_path / "no-hook.ass")
    content = output.read_text(encoding="utf-8-sig")

    assert "Dialogue: 2," not in content


def test_creator_pop_uses_reference_inspired_brand_treatment(tmp_path):
    output = write_ass_captions(
        [],
        0.0,
        20.0,
        tmp_path / "creator-pop.ass",
        hook_text="A new clip headline",
        streamer_tag="SonicInside",
    )
    content = output.read_text(encoding="utf-8-sig")

    assert "&H00962DFF" in content
    assert "A NEW CLIP HEADLINE" in content
    assert "SONICINSIDE" in content
    assert r"{\an3\pos(1008,1872)\fs34\bord6\3c&H000000&}" in content


def test_classic_style_remains_available(tmp_path):
    output = write_ass_captions(
        [],
        0.0,
        20.0,
        tmp_path / "classic.ass",
        caption_style="classic",
    )
    content = output.read_text(encoding="utf-8-sig")

    assert "Style: TikTok,Arial,64" in content
    assert "Style: Hook,Arial,58" in content

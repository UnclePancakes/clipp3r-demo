import torch

from ai_clips_maker.txtslice.tiler_algorithm import TextTiler


def test_depth_scores_use_maxima_on_both_sides_of_each_gap():
    tiler = TextTiler(device="cpu")
    gap_scores = torch.tensor([0.1, 0.4, 0.2])

    depths = tiler._calc_depth_scores(gap_scores)

    torch.testing.assert_close(depths, torch.tensor([0.3, 0.0, 0.2]))


def test_depth_scores_handle_large_inputs():
    tiler = TextTiler(device="cpu")
    gap_scores = torch.linspace(0, 1, 20_000)

    depths = tiler._calc_depth_scores(gap_scores)

    assert depths.shape == gap_scores.shape
    assert torch.isfinite(depths).all()
